import os
import sys

sys.path.insert(0, os.path.abspath("src"))
from server import get_version

def test_version():
    data = get_version()
    print("Version response:", data)
    assert data["version"] == "v3.0.0"
    assert "commit" in data
    assert "branch" in data
    assert "is_preview" in data
    print("Test passed successfully!")

if __name__ == "__main__":
    test_version()
