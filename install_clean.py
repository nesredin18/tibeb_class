import subprocess

requirements_file = "requirements.txt"

with open(requirements_file, "r") as f:
    packages = [line.strip() for line in f if line.strip() and not line.startswith("#")]

for pkg in packages:
    print(f" Installing {pkg} ...")
    result = subprocess.run(
        ["pip", "install", "--no-cache-dir", pkg],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print(f" Successfully installed {pkg}")
    else:
        print(f" Failed to install {pkg}")
        print(result.stderr)

    # Optional: clean pip cache just in case
    subprocess.run(["pip", "cache", "purge"], capture_output=True)
