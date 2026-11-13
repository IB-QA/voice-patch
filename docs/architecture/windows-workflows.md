# Windows Workflows

Diagrams for the Windows local-services design. For commands see the
[user guide](../guides/windows-local-services.md); for reasons see
[ADR 0001](adr/0001-windows-local-services.md).

## Which install path am I on?

```mermaid
flowchart TD
    S(["I want local voice on Windows"]) --> Q1{"Do I have administrator rights?"}
    Q1 -- "Yes, shell is elevated" --> A["Run installer or service install, scope auto becomes machine"]
    Q1 -- "No" --> B["Run installer or service install, scope auto becomes user"]
    A --> A1["Data in ProgramData VoiceMode"]
    A1 --> A2["Services start at boot as SYSTEM"]
    B --> B1["Data in .voicemode under my profile"]
    B1 --> B2["Services start when I log on"]
    A2 --> V["voicemode status"]
    B2 --> V
    V --> C["Configure MCP client with voicemode.exe"]
    C --> T["Try converse"]
```

## User journeys

### First install, no admin

```mermaid
flowchart TD
    A["Install uv and git"] --> B["uv tool install --editable C:\wgr\voice-patch"]
    B --> C["voicemode service install whisper"]
    C --> D["voicemode service install kokoro"]
    D --> E{"Both healthy?"}
    E -- "Yes" --> F["Add voicemode.exe to MCP client"]
    E -- "No" --> G["voicemode service logs svc"]
    G --> H{"TLS error?"}
    H -- "Yes" --> I["Set UV_SYSTEM_CERTS=1 and retry"]
    H -- "No" --> J["See troubleshooting table"]
    I --> C
    F --> K["Use converse"]
```

### Upgrade or switch scope

```mermaid
flowchart TD
    U["git pull in C:\wgr\voice-patch"] --> R["uv tool install --editable --force"]
    R --> F{"Start scripts changed?"}
    F -- "Yes" --> I["voicemode service install svc --force"]
    F -- "No" --> RS["Restart MCP client"]
    I --> RS
    X["Want a different scope"] --> UN["voicemode service uninstall svc"]
    UN --> EL["Reopen shell, elevated for machine"]
    EL --> IN["voicemode service install svc --scope ..."]
```

### Install with options

```mermaid
flowchart TD
    A["voicemode service install --help"] --> B["Pick a service"]
    B --> C["voicemode service install svc --help"]
    C --> D{"Which service?"}
    D -- "whisper" --> W["--model, --no-gpu, --force, --scope"]
    D -- "kokoro" --> K["--device auto|cpu|gpu, --port, --force, --scope"]
    D -- "voicemode" --> V["--auto-enable, --scope"]
    W --> R["Run the command"]
    K --> R
    V --> R
    R --> S["Scope resolved, files installed, task registered"]
    S --> H["voicemode status and service logs"]
```

### GPU selection

```mermaid
flowchart TD
    I["service install whisper or kokoro"] --> N{"nvidia-smi finds an NVIDIA GPU?"}
    N -- "No, --no-gpu, --device cpu" --> CPU["CPU build, .variant or .device = cpu"]
    N -- "Yes" --> WK{"Service"}
    WK -- "whisper" --> WC["CUDA 12.4 zip, start to verify"]
    WC -- "ok" --> WG["bin/.variant = cuda"]
    WC -- "fails" --> CPU
    WK -- "kokoro" --> KC["torch cu130, else cu128"]
    KC --> KV{"torch.cuda.is_available()?"}
    KV -- "Yes" --> KG[".device = cuda"]
    KV -- "No" --> CPU
    KG --> WU["First Whisper request about 45 s warm-up"]
    WG --> WU
```

See [ADR 0005](adr/0005-unified-service-install-cli-and-gpu-variants.md).

### After logon or reboot

```mermaid
flowchart TD
    P["Computer starts"] --> M{"Machine scope?"}
    M -- "Yes" --> BT["Tasks start at boot as SYSTEM"]
    M -- "No" --> W["Wait for my logon"]
    W --> LG["Tasks start at logon"]
    BT --> OK["Whisper 2022 and Kokoro 8880 listening"]
    LG --> OK
    OK --> CHK["voicemode status or Get-ScheduledTask VoiceMode-*"]
```

## Sequence: a converse call

```mermaid
sequenceDiagram
    actor User
    participant Client as MCP client
    participant VM as voicemode.exe
    participant K as Kokoro 127.0.0.1:8880
    participant W as Whisper 127.0.0.1:2022
    Client->>VM: converse(message, wait_for_response)
    VM->>K: POST /v1/audio/speech
    K-->>VM: audio stream
    VM->>User: play speech
    VM->>User: listen on microphone
    User-->>VM: speech, then silence
    VM->>W: POST /v1/audio/transcriptions
    W-->>VM: transcript
    VM-->>Client: transcript text
    Client->>VM: converse_continue or pause_conversation
```

## Sequence: starting a service

```mermaid
sequenceDiagram
    actor User
    participant CLI as voicemode service start
    participant Win as windows.py
    participant TS as Task Scheduler
    participant PS as start-svc.ps1
    participant P as Server process
    User->>CLI: start whisper
    CLI->>Win: get_task(whisper)
    Win-->>CLI: task found, scope
    CLI->>Win: start_task(whisper)
    Win->>TS: Start-ScheduledTask
    TS->>PS: run script
    PS->>PS: read voicemode.env as data, set PATH
    PS->>P: start whisper-server on port
    CLI->>CLI: wait up to 120 s for the port
    CLI-->>User: started on port 2022
```

## Task lifecycle

```mermaid
stateDiagram-v2
    [*] --> NotInstalled
    NotInstalled --> Registered: service install
    Registered --> Running: trigger or service start
    Running --> Failed: process exits non zero
    Failed --> Running: retry, 5 times, 1 min apart
    Failed --> Stopped: retries used up
    Running --> Stopped: service stop
    Stopped --> Running: service start or trigger
    Registered --> Disabled: service disable
    Stopped --> Disabled: service disable
    Disabled --> Registered: service enable
    Registered --> NotInstalled: service uninstall
    Stopped --> NotInstalled: service uninstall
    Disabled --> NotInstalled: service uninstall
```

In machine scope the trigger is "at startup" and the account is SYSTEM; in user scope the
trigger is "at logon" and the account is you. Both have no time limit.
