"""``python -m eidr_core.vendor sync|check --config vendor.toml``.

Guarded, because ``tests/test_public_api.py`` imports every module in the
package to verify ``__all__``; an unguarded ``main()`` here ran argparse at
import time and exited the test run.
"""
from eidr_core.vendor import main

if __name__ == "__main__":
    raise SystemExit(main())
