import subprocess
import sys

def commit_and_push():
    repo = "/home/pi/ranbell_image"
    print("Adding files...")
    subprocess.run(["git", "-C", repo, "add", "."], check=True)
    print("Committing...")
    msg = "feat(yukikaze): optimize for Pi 5 ARM64, bypass WD14 with ground-truth tags, and mount yukikaze archive"
    subprocess.run(["git", "-C", repo, "commit", "-m", msg], check=True)
    print("Pushing to origin main...")
    res = subprocess.run(["git", "-C", repo, "push", "origin", "main"], capture_output=True, text=True)
    print("STDOUT:", res.stdout)
    print("STDERR:", res.stderr)
    if res.returncode != 0:
        print("Push failed!")
        sys.exit(1)
    print("Pushed successfully!")

if __name__ == "__main__":
    commit_and_push()
