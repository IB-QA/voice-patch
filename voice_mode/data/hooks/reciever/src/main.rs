use std::collections::HashMap;
use std::env;
use std::fs::{self, OpenOptions};
use std::io::{self, BufRead, BufReader, Read, Write};
use std::path::PathBuf;
use chrono::Local;
fn main() {
    // Read payload from standard input pipeline
    let mut input_str = String::new();
    if io::stdin().read_to_string(&mut input_str).is_err() {
        std::process::exit(0);
    }

    // Only the voice tool. A payload that merely lists "converse" among other
    // tools, or a normal prompt, is not a voice call.
    if !invoked_tool_is_voice(&input_str) {
        std::process::exit(0);
    }

    // 2. Exact Nano/Microsecond Entry Performance Timestamps
    let start_time = std::time::Instant::now();
    let start_utc = Local::now();
    let ts_start_str = start_utc.format("%Y-%m-%dT%H:%M:%S%.9f").to_string();

    let mut client = env::var("VOICEMODE_HOOK_CLIENT").unwrap_or_else(|_| "auto".to_string());
    let mut debug = false;
    let args: Vec<String> = env::args().collect();
    let mut i = 1;
    while i < args.len() {
        if args[i] == "--client" && i + 1 < args.len() {
            client = args[i + 1].clone();
            i += 2;
        } else if args[i].starts_with("--client=") {
            client = args[i].split_at(9).1.to_string();
            i += 1;
        } else if args[i] == "--debug" || args[i] == "--debug=true" {
            debug = true;
            i += 1;
        } else {
            i += 1;
        }
    }

    let run_res = run_pipeline(&input_str, &client);
    let stdout_json = match &run_res {
        Ok(Some(s)) => serde_json::from_str::<serde_json::Value>(s).ok(),
        _ => None,
    };
    let updated_input = stdout_json.as_ref().and_then(|v| {
        v.get("updated_input")
            .or_else(|| v.get("modifiedArgs"))
            .or_else(|| v.pointer("/hookSpecificOutput/updatedInput"))
            .cloned()
    });

    // 3. Output Duration Metrics to stderr and dynamic metadata logs
    let elapsed_ns = start_time.elapsed().as_nanos();
    let end_utc = Local::now();
    let ts_end_str = end_utc.format("%Y-%m-%dT%H:%M:%S%.9f").to_string();
    if debug {
        eprintln!("[RUST END] Execution took {}ms ({} ns)", elapsed_ns / 1_000_000, elapsed_ns);
    }

    let home = env::var("HOME").unwrap_or_default();
    let mut log_path = PathBuf::from(&home);
    log_path.push(".voicemode/logs/converse-pre-tool-use.jsonl");
    let _ = fs::create_dir_all(log_path.parent().unwrap());

    // The log copies every spoken message, so "leave no trace" turns it off.
    if !keep_history() {
        if let Ok(Some(output_payload)) = run_res {
            println!("{}", output_payload);
        }
        return;
    }

    if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(&log_path) {
        if let Ok(parsed_json) = serde_json::from_str::<serde_json::Value>(&input_str) {
            let log_obj = serde_json::json!({
                "prefix": "[RUST]",
                "ts_start": ts_start_str,
                "ts_end": ts_end_str,
                "elapsed_ns": elapsed_ns,
                "client": client,
                "payload": parsed_json,
                "updated_input": updated_input,
                "stdout": stdout_json,
            });
            if let Ok(line) = serde_json::to_string(&log_obj) {
                let _ = writeln!(file, "{}", line);
            }
        }
    }

    if let Ok(Some(output_payload)) = run_res {
        if debug {
            eprintln!("[RUST STDOUT] {}", output_payload);
        }
        println!("{}", output_payload);
    }
}

fn keep_history() -> bool {
    let home = env::var("HOME").unwrap_or_default();
    let configs = read_env_file(&format!("{}/.voicemode/voicemode.env", home));
    env::var("VOICEMODE_KEEP_HISTORY")
        .ok()
        .or_else(|| configs.get("VOICEMODE_KEEP_HISTORY").cloned())
        .map(|v| is_truthy(&v))
        .unwrap_or(true)
}

fn run_pipeline(input_str: &str, client_arg: &str) -> Result<Option<String>, Box<dyn std::error::Error>> {
    let mut client = client_arg.to_string();
    let mut data: serde_json::Value = match serde_json::from_str(input_str) {
        Ok(v) => v,
        Err(_) => return Ok(None),
    };

    let home = env::var("HOME").unwrap_or_default();
    let env_file_path = format!("{}/.voicemode/voicemode.env", home);
    let configs = read_env_file(&env_file_path);

    let get_config = |k1: &str, k2: &str| -> Option<String> {
        env::var(k1).ok()
            .or_else(|| env::var(k2).ok())
            .or_else(|| configs.get(k1).cloned())
            .or_else(|| configs.get(k2).cloned())
    };

    let force = get_config("VOICEMODE_FORCE_WAIT_FOR_RESPONSE", "FORCE_WAIT_FOR_RESPONSE")
        .map(|v| is_truthy(&v)).unwrap_or(true);
    let strip = get_config("VOICEMODE_STRIP_LISTEN_DURATION_MAX", "STRIP_LISTEN_DURATION_MAX")
        .map(|v| is_truthy(&v)).unwrap_or(true);
    let default_listen: f64 = get_config("VOICEMODE_DEFAULT_LISTEN_DURATION", "DEFAULT_LISTEN_DURATION")
        .and_then(|v| v.parse().ok()).unwrap_or(120.0);

    if !force && !strip { return Ok(None); }

    if client == "auto" {
        client = if env::var("GITHUB_COPILOT_API_TOKEN").is_ok() || env::var("COPILOT_CLI").is_ok() { "copilot".to_string() } else
        if env::var("CURSOR_AGENT").is_ok() || env::var("CURSOR_TRACE_ID").is_ok() { "cursor".to_string() } else
        if env::var("CODEX_HOME").is_ok() || env::var("CODEX_THREAD_ID").is_ok() { "codex".to_string() } else
        if env::var("CLAUDECODE").is_ok() || env::var("CLAUDE_PLUGIN_ROOT").is_ok() { "claude".to_string() } else { "claude".to_string() };
    }

    let name = get_nested_string(&data, &["tool_name"])
        .or_else(|| get_nested_string(&data, &["toolName"]))
        .or_else(|| get_nested_string(&data, &["toolCall", "name"]))
        .unwrap_or_default();

    let inner_name = get_nested_string(&data, &["tool_input", "name"])
        .or_else(|| get_nested_string(&data, &["tool_input", "toolName"]))
        .or_else(|| get_nested_string(&data, &["toolArgs", "name"]))
        .unwrap_or_default();

    if !is_converse(&name) && !is_converse(&inner_name) { return Ok(None); }
    if data.get("toolCall").is_some() { return Ok(None); }

    let mut updated_input = serde_json::Value::Null;
    let has_tool_input = data.get("tool_input").is_some();
    
    let nested_name = if has_tool_input {
        get_nested_string(&data, &["tool_input", "name"])
            .or_else(|| get_nested_string(&data, &["tool_input", "toolName"]))
            .unwrap_or_default()
    } else { String::new() };

    if has_tool_input && is_converse(&nested_name) {
        if let Some(tool_input) = data.get_mut("tool_input") {
            if let Some(arguments) = tool_input.get_mut("arguments") {
                if arguments.is_object() {
                    apply_mutations(arguments, force, strip, default_listen);
                    updated_input = tool_input.clone();
                }
            }
        }
    } else {
        let mut target = if let Some(ti) = data.get_mut("tool_input") { ti.clone() } else
        if let Some(ta) = data.get_mut("toolArgs") { ta.clone() } else
        if let Some(arg) = data.get_mut("arguments") { arg.clone() } else {
            serde_json::Value::Object(serde_json::Map::new())
        };
        apply_mutations(&mut target, force, strip, default_listen);
        updated_input = target;
    }

    if client == "antigravity" { return Ok(None); }

    let output = match client.as_str() {
        "cursor" => serde_json::json!({ "permission": "allow", "updated_input": updated_input }),
        "copilot" => serde_json::json!({ "permissionDecision": "allow", "modifiedArgs": updated_input }),
        _ => serde_json::json!({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse", "permissionDecision": "allow", "updatedInput": updated_input
            }
        }),
    };

    Ok(Some(serde_json::to_string(&output)?))
}

fn invoked_tool_is_voice(input: &str) -> bool {
    let data: serde_json::Value = match serde_json::from_str(input) {
        Ok(v) => v,
        Err(_) => return false,
    };
    let names = [
        get_nested_string(&data, &["tool_name"]),
        get_nested_string(&data, &["toolName"]),
        get_nested_string(&data, &["toolCall", "name"]),
        get_nested_string(&data, &["tool_input", "name"]),
        get_nested_string(&data, &["toolArgs", "name"]),
    ];
    names.into_iter().flatten().any(|name| is_converse(&name))
}

fn is_converse(s: &str) -> bool {
    let lower = s.to_lowercase();
    let tail = lower.rsplit(['/', ':']).next().unwrap_or(&lower);
    let tail = tail.rsplit("__").next().unwrap_or(tail);
    // Only `converse`. `converse_continue` takes just job_id and wait_seconds, so
    // adding converse's arguments to it makes the call fail validation.
    tail == "converse"
}

fn is_truthy(s: &str) -> bool {
    let normalized = s.trim().to_lowercase().replace('"', "").replace('\'', "");
    matches!(normalized.as_str(), "true" | "1" | "yes" | "on")
}

fn apply_mutations(val: &mut serde_json::Value, force: bool, strip: bool, default_listen: f64) {
    if let Some(obj) = val.as_object_mut() {
        // 1. Process Base Object Level
        if force {
            match obj.get("wait_for_response") {
                Some(serde_json::Value::Bool(true)) => {} // Already true, no tension
                _ => {
                    obj.insert("wait_for_response".to_string(), serde_json::Value::Bool(true));
                }
            }
        }
        // Cursor merges updated_input; omitting a key keeps the original value.
        // Overwrite listen_duration_max with the server default so the cap changes.
        if strip {
            // Cursor merges updated_input; omitted keys keep the agent value.
            obj.insert(
                "listen_duration_max".to_string(),
                serde_json::json!(default_listen),
            );
            obj.insert("listen_duration_min".to_string(), serde_json::json!(2.0));
            obj.insert("vad_aggressiveness".to_string(), serde_json::json!(3));
            obj.insert(
                "disable_silence_detection".to_string(),
                serde_json::Value::Bool(false),
            );
            obj.insert("timeout".to_string(), serde_json::json!(60.0));
        }

        // 2. Process Nested Array Object Level ("turns")
        if let Some(turns) = obj.get_mut("turns").and_then(|t| t.as_array_mut()) {
            for turn in turns {
                if let Some(t_obj) = turn.as_object_mut() {
                    if force {
                        match t_obj.get("wait_for_response") {
                            Some(serde_json::Value::Bool(true)) => {}
                            _ => {
                                t_obj.insert("wait_for_response".to_string(), serde_json::Value::Bool(true));
                            }
                        }
                    }
                    if strip {
                        t_obj.insert(
                            "listen_duration_max".to_string(),
                            serde_json::json!(default_listen),
                        );
                        t_obj.insert("listen_duration_min".to_string(), serde_json::json!(2.0));
                        t_obj.insert("vad_aggressiveness".to_string(), serde_json::json!(3));
                        t_obj.insert(
                            "disable_silence_detection".to_string(),
                            serde_json::Value::Bool(false),
                        );
                        t_obj.insert("timeout".to_string(), serde_json::json!(60.0));
                    }
                }
            }
        }
    }
}


fn get_nested_string(val: &serde_json::Value, keys: &[&str]) -> Option<String> {
    let mut current = val;
    for &key in keys { current = current.get(key)?; }
    current.as_str().map(|s| s.to_string())
}

fn read_env_file(path: &str) -> HashMap<String, String> {
    let mut map = HashMap::new();
    if let Ok(file) = std::fs::File::open(path) {
        let reader = BufReader::new(file);
        for line in reader.lines().map_while(Result::ok) {
            let trimmed = line.trim();
            if trimmed.is_empty() || trimmed.starts_with('#') { continue; }
            let parts: Vec<&str> = trimmed.splitn(2, '=').collect();
            if parts.len() == 2 {
                map.insert(parts[0].trim().to_string(), parts[1].trim().trim_matches(|c| c == '"' || c == '\'').to_string());
            }
        }
    }
    map
}
