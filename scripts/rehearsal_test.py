import os
import subprocess
import sys
from rehearsal_manage import cfg, root

if __name__ == "__main__":
    env = dict(
        os.environ,
        **{k: v for k, v in cfg.items() if v is not None},
        PYTHONIOENCODING="utf-8"
    )
    sys.exit(
        subprocess.call(
            [sys.executable, "-m", "pytest", *sys.argv[1:]],
            cwd=root / "backend",
            env=env,
        )
    )
