import subprocess
import sys

def main():
    print("Checking if ponderingm/ranbell_image already exists...")
    check_res = subprocess.run(
        ["gh", "repo", "view", "ponderingm/ranbell_image"],
        capture_output=True, text=True
    )
    if check_res.returncode == 0:
        print("Repository ponderingm/ranbell_image already exists on GitHub.")
    else:
        print("Forking ranbell/ranbell_image to ponderingm/ranbell_image...")
        fork_res = subprocess.run(
            ["gh", "repo", "fork", "ranbell/ranbell_image", "--clone=false"],
            capture_output=True, text=True
        )
        print("Fork output:", fork_res.stdout, fork_res.stderr)
        if fork_res.returncode != 0:
            print("Failed to fork repository.")
            sys.exit(1)

    # Clone to /home/pi/ranbell_image if not already present
    import os
    target_dir = "/home/pi/ranbell_image"
    if os.path.exists(target_dir):
        print(f"Directory {target_dir} already exists.")
    else:
        print(f"Cloning ponderingm/ranbell_image to {target_dir}...")
        clone_res = subprocess.run(
            ["gh", "repo", "clone", "ponderingm/ranbell_image", target_dir],
            capture_output=True, text=True
        )
        print("Clone output:", clone_res.stdout, clone_res.stderr)
        if clone_res.returncode != 0:
            print("Failed to clone repository.")
            sys.exit(1)

    print("Fork and clone completed successfully.")

if __name__ == "__main__":
    main()
