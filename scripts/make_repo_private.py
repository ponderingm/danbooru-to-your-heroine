import subprocess

def make_repo_private():
    print("Setting ponderingm/ranbell_image visibility to private...")
    # Note: gh repo edit interactive prompt can be bypassed by sending 'y\n' or using gh api
    res = subprocess.run(
        ["gh", "repo", "edit", "ponderingm/ranbell_image", "--visibility", "private"],
        input="y\n",
        capture_output=True, text=True
    )
    print("STDOUT:", res.stdout)
    print("STDERR:", res.stderr)
    print("Return code:", res.returncode)

if __name__ == "__main__":
    make_repo_private()
