import os
import sys
import subprocess

def test_validation():
    print("=========================================================="
          "\nFail-Fast Test: Validating Invalid Environment Variables"
          "\n==========================================================")
    
    # Run a subprocess with custom broken env vars to see if it fails fast
    env = os.environ.copy()
    
    # Case 1: Missing required variable (e.g. DATABASE_URL)
    print("Case 1: Missing DATABASE_URL...")
    env_missing = env.copy()
    # Force loading with custom environment settings that trigger failures
    env_missing["ENV_FILE"] = ".nonexistent_file"
    if "DATABASE_URL" in env_missing:
        del env_missing["DATABASE_URL"]
    if "REDIS_URL" in env_missing:
        del env_missing["REDIS_URL"]
    if "MINIO_ENDPOINT" in env_missing:
        del env_missing["MINIO_ENDPOINT"]
        
    proc = subprocess.run(
        [sys.executable, "-c", "import sys; sys.path.append('.'); from backend.app.core.config import Settings; Settings()"],
        env=env_missing,
        capture_output=True,
        text=True
    )
    
    if proc.returncode != 0:
        print("   [OK] Settings initialization failed on boot as expected.")
        if "ValidationError" in proc.stderr or "validation error" in proc.stderr:
            print("   [OK] ValidationError trace caught cleanly:")
            lines = [line.strip() for line in proc.stderr.split("\n") if "Field required" in line or "database_url" in line or "ValidationError" in line or "Input should be" in line]
            for l in lines:
                print(f"         -> {l}")
        else:
            print(f"   [WARNING] Boot failed but stderr did not match expected structure. Stderr:\n{proc.stderr}")
    else:
        print("   [FAILED] App booted successfully despite missing vital credentials!")

if __name__ == "__main__":
    test_validation()
