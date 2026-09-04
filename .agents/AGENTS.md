# Project-Scoped Rules

## Version Compilation and Server Deployment
Every time a new version is compiled (by running PyInstaller on `emojinoko_monitor.py` or `standalone_pet.py`), the assistant must automatically perform the following steps:
1. Update `version.json` in `\\power2\RD Share\EdwinLuo\Another Token Bites the Dust` with the new version number (`CURRENT_VERSION`), download URL, and changelog.
2. Copy the newly compiled `TokenPet.exe` from `D:\token_monitor\dist\TokenPet.exe` to `\\power2\RD Share\EdwinLuo\Another Token Bites the Dust\TokenPet.exe`.
