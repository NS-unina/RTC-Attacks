#!/usr/bin/env python3
"""
Sync timezone configuration across all Docker Compose files.

This script adds /etc/localtime and /etc/timezone volume mounts to all
services in scenario docker-compose.yaml files to ensure containers use
the host's timezone instead of UTC.

Usage:
    python3 scripts/sync_timezone_compose.py
    python3 scripts/sync_timezone_compose.py --dry-run  # Preview changes
"""

import sys
from pathlib import Path
import yaml


def add_timezone_volumes(compose_data):
    """Add timezone volume mounts to all services in compose data."""
    if 'services' not in compose_data:
        return False
    
    modified = False
    timezone_volumes = [
        '/etc/localtime:/etc/localtime:ro',
        '/etc/timezone:/etc/timezone:ro'
    ]
    
    for service_name, service_config in compose_data['services'].items():
        if service_config is None:
            service_config = {}
            compose_data['services'][service_name] = service_config
        
        # Get or create volumes list
        if 'volumes' not in service_config:
            service_config['volumes'] = []
        
        volumes = service_config['volumes']
        if volumes is None:
            volumes = []
            service_config['volumes'] = volumes
        
        # Check if timezone volumes already exist
        existing = [str(v).split(':')[0] for v in volumes if ':' in str(v)]
        
        for tz_vol in timezone_volumes:
            source = tz_vol.split(':')[0]
            if source not in existing:
                volumes.append(tz_vol)
                modified = True
                print(f"  Added {tz_vol} to service '{service_name}'")
    
    return modified


def process_compose_file(file_path: Path, dry_run=False):
    """Process a single docker-compose.yaml file."""
    print(f"\nProcessing: {file_path}")
    
    try:
        with open(file_path, 'r') as f:
            compose_data = yaml.safe_load(f)
        
        if compose_data is None:
            print(f"  WARNING: Empty or invalid YAML file")
            return False
        
        modified = add_timezone_volumes(compose_data)
        
        if modified:
            if not dry_run:
                with open(file_path, 'w') as f:
                    yaml.dump(compose_data, f, default_flow_style=False, sort_keys=False)
                print(f"  ✅ Updated: {file_path}")
            else:
                print(f"  [DRY RUN] Would update: {file_path}")
            return True
        else:
            print(f"  ℹ️  No changes needed (timezone volumes already present)")
            return False
    
    except Exception as e:
        print(f"  ❌ ERROR: {e}")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Sync timezone across Docker Compose files")
    parser.add_argument('--dry-run', action='store_true', help='Show what would be changed without modifying files')
    parser.add_argument('--repo-root', type=Path, default=Path.cwd(), help='Repository root path')
    args = parser.parse_args()
    
    repo_root = args.repo_root
    
    # Find all docker-compose.yaml files in public/labs
    labs_dir = repo_root / 'public' / 'labs'
    if not labs_dir.exists():
        print(f"ERROR: Labs directory not found: {labs_dir}")
        sys.exit(1)
    
    compose_files = sorted(labs_dir.glob('*/docker-compose.yaml'))
    
    if not compose_files:
        print(f"WARNING: No docker-compose.yaml files found in {labs_dir}")
        sys.exit(0)
    
    print(f"Found {len(compose_files)} docker-compose.yaml files")
    print("\nNOTE: Comments in YAML files may not be preserved (using PyYAML)")
    print("="*60)
    
    modified_count = 0
    for compose_file in compose_files:
        if process_compose_file(compose_file, dry_run=args.dry_run):
            modified_count += 1
    
    print("\n" + "="*60)
    print(f"\nSummary:")
    print(f"  Total files: {len(compose_files)}")
    print(f"  Modified: {modified_count}")
    print(f"  Unchanged: {len(compose_files) - modified_count}")
    
    if args.dry_run:
        print("\n⚠️  DRY RUN mode - no files were actually modified")
        print("   Run without --dry-run to apply changes")
    else:
        print("\n✅ Timezone sync complete")
        print("   Restart containers to apply: make cleanup-all && make start-suricata")


if __name__ == '__main__':
    main()
