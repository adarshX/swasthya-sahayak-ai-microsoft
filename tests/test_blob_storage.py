"""
TEST: Azure Blob Storage
Checks: connection, container exists/create, upload, download, delete
Run:  python tests/test_blob_storage.py
"""

import json
import os
import sys
import uuid

# Load .env manually (no python-dotenv dependency)
def load_env(path=".env"):
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

load_env()

CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
CONTAINER_NAME    = os.getenv("AZURE_BLOB_CONTAINER", "visit-records")

PASS = "\033[92m  PASS\033[0m"
FAIL = "\033[91m  FAIL\033[0m"
INFO = "\033[94m  INFO\033[0m"

def check(label, fn):
    try:
        result = fn()
        print(f"{PASS}  {label}" + (f" -> {result}" if result else ""))
        return True
    except Exception as e:
        print(f"{FAIL}  {label} -> {e}")
        return False

def main():
    print("\n=== Azure Blob Storage Test ===\n")

    if not CONNECTION_STRING:
        print(f"{FAIL}  AZURE_STORAGE_CONNECTION_STRING is not set in .env")
        sys.exit(1)
    print(f"{INFO}  Connection string found (account: {CONNECTION_STRING.split(';')[1].split('=')[1]})")

    try:
        from azure.storage.blob import BlobServiceClient
    except ImportError:
        print(f"{FAIL}  azure-storage-blob not installed -> run: pip install azure-storage-blob")
        sys.exit(1)

    client = BlobServiceClient.from_connection_string(CONNECTION_STRING)
    container = client.get_container_client(CONTAINER_NAME)
    test_blob = f"test-{uuid.uuid4()}.json"
    test_data = json.dumps({"test": True, "patient_id": "test-001", "triage": "Home Care"})

    results = []
    results.append(check("Connect to storage account",
        lambda: client.get_account_information()))

    def ensure_container():
        try:
            container.create_container()
            return "created"
        except Exception as e:
            if "ContainerAlreadyExists" in str(e):
                return "already exists (ok)"
            raise

    results.append(check(f"Get/create container '{CONTAINER_NAME}'", ensure_container))

    results.append(check(f"Upload blob '{test_blob}'",
        lambda: container.upload_blob(test_blob, test_data, overwrite=True) or "uploaded"))

    results.append(check("Download and verify blob",
        lambda: "content matches" if json.loads(
            container.download_blob(test_blob).readall()
        )["triage"] == "Home Care" else (_ for _ in ()).throw(Exception("content mismatch"))))

    results.append(check("List blobs in container",
        lambda: f"{sum(1 for _ in container.list_blobs())} blob(s) found"))

    results.append(check(f"Delete test blob",
        lambda: container.delete_blob(test_blob) or "deleted"))

    print(f"\n{'='*35}")
    passed = sum(results)
    print(f"  Result: {passed}/{len(results)} checks passed")
    if passed == len(results):
        print(f"\033[92m  Blob Storage is correctly configured.\033[0m\n")
    else:
        print(f"\033[91m  Blob Storage has issues — check errors above.\033[0m\n")

if __name__ == "__main__":
    main()
