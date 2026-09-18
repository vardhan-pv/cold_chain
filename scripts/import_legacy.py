"""Archive older SQLite records losslessly, without replaying old commands."""
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.archive import import_legacy
from backend.service import Service

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--database-url', default=f'sqlite:///{ROOT / "runtime/cold_chain.db"}')
    args = parser.parse_args()
    (ROOT/'runtime').mkdir(exist_ok=True)
    service = Service(args.database_url)
    try:
        print(json.dumps(import_legacy(service, args.source), indent=2))
    finally:
        service.engine.dispose()

if __name__ == '__main__':
    main()
