#!/usr/bin/env python3
"""
HLS Knowledge Base Logger-Rollback Tool (v1.0)

Automated tool for generating rollback logs and executing rollbacks.

Functions:
  logger:   Automatically generate rollback log from database records
  rollback: Execute rollback from log file

Usage:
  # Generate log for specific project and iteration
  python3 logger-rollback.py logger --project FIR128 --iteration 4
  
  # Generate log for recent imports (last 1 hour)
  python3 logger-rollback.py logger --recent 1h
  
  # Execute rollback (with confirmation)
  python3 logger-rollback.py rollback logs/rollback_FIR128_iter4_20251012.yaml
  
  # Dry run (preview only)
  python3 logger-rollback.py rollback --dry-run logs/rollback_FIR128_iter4_20251012.yaml
"""

import sys
import yaml
import asyncio
import asyncpg
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class LoggerRollback:
    """Automated Logger and Rollback Tool"""
    
    # Tables that can be rolled back (hls_rules is excluded)
    ROLLBACK_TABLES = [
        "design_iterations",
        "design_patterns",
        "projects",
        "rules_effectiveness",
        "synthesis_results"
    ]
    
    # Rollback order (child → parent, respecting FK constraints)
    ROLLBACK_ORDER = [
        "synthesis_results",      # FK: iteration_id → design_iterations
        "rules_effectiveness",    # FK: rule_id → hls_rules (but we don't delete rules)
        "design_iterations",      # FK: project_id → projects
        "design_patterns",        # No FK to other rollback tables
        "projects"                # No FK
    ]
    
    def __init__(self, db_url: str, force: bool = False):
        self.db_url = db_url
        self.conn = None
        self.force = force
    
    async def connect(self):
        """Connect to database"""
        self.conn = await asyncpg.connect(self.db_url)
        print("[✓] Connected to database")
    
    async def close(self):
        """Close database connection"""
        if self.conn:
            await self.conn.close()
            print("[✓] Database connection closed")
    
    # ========================================================================
    # LOGGER FUNCTIONS
    # ========================================================================
    
    async def logger_by_project(self, project_name: str, iteration: Optional[int] = None) -> str:
        """
        Generate rollback log for specific project and iteration.
        
        Args:
            project_name: Project name (e.g., "FIR128_Optimization_Demo")
            iteration: Iteration number (optional, if None will log all recent)
        
        Returns:
            Path to generated log file
        """
        # Find project
        project = await self.conn.fetchrow(
            "SELECT * FROM projects WHERE name = $1 ORDER BY created_at DESC LIMIT 1",
            project_name
        )
        
        if not project:
            print(f"[✘] Project not found: {project_name}")
            return None
        
        project_id = project['id']
        
        # Find iterations
        if iteration:
            iterations = await self.conn.fetch(
                "SELECT * FROM design_iterations WHERE project_id = $1 AND iteration_number = $2",
                project_id, iteration
            )
        else:
            iterations = await self.conn.fetch(
                "SELECT * FROM design_iterations WHERE project_id = $1 ORDER BY created_at DESC",
                project_id
            )
        
        if not iterations:
            print(f"[✘] No iterations found for project: {project_name}")
            return None
        
        # Collect all records to log
        records = []
        
        # Add project
        records.append({
            "table": "projects",
            "id": str(project['id']),
            "note": f"Project: {project['name']}"
        })
        
        # Add iterations and related records
        for iter_row in iterations:
            iter_id = iter_row['id']
            
            # Add iteration
            records.append({
                "table": "design_iterations",
                "id": str(iter_id),
                "note": f"Iteration #{iter_row['iteration_number']}: {iter_row['approach_description'][:50] if iter_row['approach_description'] else 'N/A'}"
            })
            
            # Add synthesis results
            synth = await self.conn.fetch(
                "SELECT * FROM synthesis_results WHERE iteration_id = $1",
                iter_id
            )
            for s in synth:
                records.append({
                    "table": "synthesis_results",
                    "id": str(s['id']),
                    "note": f"Synthesis: II={s['ii_achieved']}"
                })
        
        # Add rules_effectiveness (for this project type)
        rules_eff = await self.conn.fetch(
            "SELECT * FROM rules_effectiveness WHERE project_type = $1",
            project['type']
        )
        for r in rules_eff:
            records.append({
                "table": "rules_effectiveness",
                "id": str(r['id']),
                "note": f"Rule effectiveness for {project['type']}"
            })
        
        # Generate log file
        log_path = self._generate_log_file(
            project_name=project['name'],
            project_type=project['type'],
            iteration=iteration,
            records=records
        )
        
        return log_path
    
    async def logger_recent(self, hours: float = 1.0) -> str:
        """
        Generate rollback log for recent imports (last N hours).
        
        Args:
            hours: Number of hours to look back
        
        Returns:
            Path to generated log file
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        records = []
        
        # Query each table for recent records
        for table in self.ROLLBACK_TABLES:
            # rules_effectiveness uses last_applied_at instead of created_at
            if table == "rules_effectiveness":
                time_column = "last_applied_at"
            else:
                time_column = "created_at"
            
            try:
                rows = await self.conn.fetch(
                    f"SELECT * FROM {table} WHERE {time_column} > $1 ORDER BY {time_column} DESC",
                    cutoff_time
                )
                
                for row in rows:
                    note = self._generate_note(table, row)
                    records.append({
                        "table": table,
                        "id": str(row['id']),
                        "note": note
                    })
            except Exception as e:
                print(f"[!] Warning: Could not query {table}: {e}")
                continue
        
        if not records:
            print(f"[✘] No records found in last {hours} hour(s)")
            return None
        
        # Generate log file
        log_path = self._generate_log_file(
            project_name="RECENT",
            project_type="mixed",
            iteration=None,
            records=records,
            notes=f"Recent imports from last {hours} hour(s)"
        )
        
        return log_path
    
    def _generate_note(self, table: str, row: Dict) -> str:
        """Generate human-readable note for a record"""
        if table == "projects":
            return f"Project: {row.get('name', 'N/A')}"
        elif table == "design_iterations":
            return f"Iteration #{row.get('iteration_number', '?')}"
        elif table == "synthesis_results":
            return f"Synthesis: II={row.get('ii_achieved', '?')}"
        elif table == "rules_effectiveness":
            return f"Rule effectiveness: {row.get('project_type', '?')}"
        elif table == "design_patterns":
            return f"Pattern: {row.get('name', 'N/A')}"
        else:
            return "Record"
    
    def _generate_log_file(
        self,
        project_name: str,
        project_type: str,
        iteration: Optional[int],
        records: List[Dict],
        notes: str = ""
    ) -> str:
        """Generate YAML log file"""
        
        # Create logs directory
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if iteration:
            filename = f"rollback_{project_name}_iter{iteration}_{timestamp}.yaml"
        else:
            filename = f"rollback_{project_name}_{timestamp}.yaml"
        
        log_path = logs_dir / filename
        
        # Check if similar log already exists (avoid duplicates)
        if self._check_duplicate_log(project_name, iteration):
            existing = list(logs_dir.glob(f"rollback_{project_name}_iter{iteration}_*.yaml"))
            if existing:
                print(f"[!] Warning: Similar log already exists: {existing[0]}")
                if not self.force:
                    response = input("Create new log anyway? [y/N]: ").strip().lower()
                    if response not in ['y', 'yes']:
                        print("[!] Log creation cancelled")
                        return None
                else:
                    print("[!] Force mode: Creating new log anyway")
        
        # Create log data
        log_data = {
            "project": project_name,
            "iteration": iteration,
            "project_type": project_type,
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),
            "operator": "logger-rollback.py",
            "notes": notes or f"Auto-generated log for {project_name}",
            "inserted_records": records,
            "rollback_status": "pending"
        }
        
        # Write log file
        with open(log_path, 'w', encoding='utf-8') as f:
            yaml.dump(log_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        print(f"\n[✓] Rollback log created: {log_path}")
        print(f"[!] Records to rollback: {len(records)}")
        
        # Show summary
        table_counts = {}
        for record in records:
            table = record['table']
            table_counts[table] = table_counts.get(table, 0) + 1
        
        print("\n[!] Summary by table:")
        for table, count in table_counts.items():
            print(f"    {table}: {count}")
        
        return str(log_path)
    
    def _check_duplicate_log(self, project_name: str, iteration: Optional[int]) -> bool:
        """Check if similar log already exists"""
        logs_dir = Path("logs")
        if not logs_dir.exists():
            return False
        
        if iteration:
            pattern = f"rollback_{project_name}_iter{iteration}_*.yaml"
        else:
            pattern = f"rollback_{project_name}_*.yaml"
        
        return len(list(logs_dir.glob(pattern))) > 0
    
    # ========================================================================
    # ROLLBACK FUNCTIONS
    # ========================================================================
    
    async def rollback(self, log_file: str, dry_run: bool = False) -> bool:
        """
        Execute rollback from log file.
        
        Args:
            log_file: Path to YAML log file
            dry_run: If True, only preview changes
        
        Returns:
            True if successful
        """
        # Read log file
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                log_data = yaml.safe_load(f)
        except Exception as e:
            print(f"[✘] Failed to read log file: {e}")
            return False
        
        # Check rollback status
        if log_data.get('rollback_status') == 'completed':
            print("[!] Warning: This log has already been rolled back")
            response = input("Continue anyway? [y/N]: ").strip().lower()
            if response not in ['y', 'yes']:
                return False
        
        # Display summary
        self._display_summary(log_data)
        
        # Execute rollback
        if dry_run:
            print("\n[!] DRY RUN MODE - No actual changes\n")
            self._dry_run_rollback(log_data)
            return True
        else:
            # Confirm
            response = input("\nProceed with rollback? [y/N]: ").strip().lower()
            if response not in ['y', 'yes']:
                print("[!] Rollback cancelled")
                return False
            
            return await self._execute_rollback(log_data, log_file)
    
    def _display_summary(self, log_data: Dict):
        """Display rollback summary"""
        print("\n" + "="*70)
        print("  ROLLBACK SUMMARY")
        print("="*70)
        print(f"  Project: {log_data.get('project', 'N/A')}")
        print(f"  Iteration: #{log_data.get('iteration', 'N/A')}")
        print(f"  Date: {log_data.get('date', 'N/A')}")
        print(f"  Timestamp: {log_data.get('timestamp', 'N/A')}")
        
        records = log_data.get('inserted_records', [])
        print(f"\n  Records to delete: {len(records)}")
        
        # Group by table
        table_counts = {}
        for record in records:
            table = record.get('table')
            table_counts[table] = table_counts.get(table, 0) + 1
        
        for table, count in table_counts.items():
            print(f"    - {table}: {count}")
        
        print("="*70)
    
    def _dry_run_rollback(self, log_data: Dict):
        """Dry run - show what would be done"""
        records = log_data.get('inserted_records', [])
        
        # Determine rollback order
        rollback_order = self._determine_order(records)
        
        print("Rollback order:")
        for i, table in enumerate(rollback_order, 1):
            print(f"  {i}. {table}")
        
        print("\nSQL statements to execute:\n")
        
        for table in rollback_order:
            table_records = [r for r in records if r['table'] == table]
            for record in table_records:
                rec_id = record.get('id')
                note = record.get('note', '')
                print(f"  DELETE FROM {table} WHERE id = '{rec_id}';  -- {note}")
    
    async def _execute_rollback(self, log_data: Dict, log_file: str) -> bool:
        """Execute actual rollback"""
        records = log_data.get('inserted_records', [])
        
        try:
            # Start transaction
            async with self.conn.transaction():
                print("\n[!] Starting rollback transaction...\n")
                
                # Rollback in correct order
                rollback_order = self._determine_order(records)
                
                for table in rollback_order:
                    table_records = [r for r in records if r['table'] == table]
                    
                    for record in table_records:
                        rec_id = record.get('id')
                        note = record.get('note', '')
                        
                        sql = f"DELETE FROM {table} WHERE id = $1"
                        
                        print(f"  [✓] Deleting from {table}: {rec_id[:8]}... ({note})")
                        await self.conn.execute(sql, rec_id)
                
                print(f"\n[✓] Transaction completed successfully")
            
            # Update log file status
            self._update_log_status(log_file, log_data)
            
            return True
            
        except Exception as e:
            print(f"\n[✘] Rollback failed: {e}")
            print(f"[!] Transaction rolled back - no changes were made")
            return False
    
    def _determine_order(self, records: List[Dict]) -> List[str]:
        """Determine rollback order (child → parent)"""
        tables = set(r['table'] for r in records)
        return [t for t in self.ROLLBACK_ORDER if t in tables]
    
    def _update_log_status(self, log_file: str, log_data: Dict):
        """Update log file to mark as rolled back"""
        log_data['rollback_status'] = 'completed'
        log_data['rollback_timestamp'] = datetime.now().isoformat()
        
        with open(log_file, 'w', encoding='utf-8') as f:
            yaml.dump(log_data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        print(f"[✓] Log file updated: {log_file}")


async def main():
    parser = argparse.ArgumentParser(
        description="HLS Knowledge Base Logger-Rollback Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate log for specific project and iteration
  python3 logger-rollback.py logger --project FIR128_Optimization_Demo --iteration 4
  
  # Generate log for recent imports (last 1 hour)
  python3 logger-rollback.py logger --recent 1h
  
  # Execute rollback (with confirmation)
  python3 logger-rollback.py rollback logs/rollback_FIR128_iter4_20251012.yaml
  
  # Dry run (preview only)
  python3 logger-rollback.py rollback --dry-run logs/rollback_FIR128_iter4_20251012.yaml
"""
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Logger command
    logger_parser = subparsers.add_parser('logger', help='Generate rollback log')
    logger_parser.add_argument(
        '--project',
        help='Project name (e.g., FIR128_Optimization_Demo)'
    )
    logger_parser.add_argument(
        '--iteration',
        type=int,
        help='Iteration number (optional)'
    )
    logger_parser.add_argument(
        '--recent',
        help='Generate log for recent imports (e.g., 1h, 2h, 24h)'
    )
    logger_parser.add_argument(
        '--force',
        action='store_true',
        help='Force creation without confirmation prompts'
    )
    logger_parser.add_argument(
        '--db-url',
        default="postgresql://hls_user:hls_pass_2024@localhost:5432/hls_knowledge",
        help='Database connection URL'
    )
    
    # Rollback command
    rollback_parser = subparsers.add_parser('rollback', help='Execute rollback from log')
    rollback_parser.add_argument(
        'log_file',
        help='Path to rollback log file (YAML)'
    )
    rollback_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    rollback_parser.add_argument(
        '--db-url',
        default="postgresql://hls_user:hls_pass_2024@localhost:5432/hls_knowledge",
        help='Database connection URL'
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Execute command
    if args.command == 'logger':
        if not args.project and not args.recent:
            print("[✘] Error: Must specify --project or --recent")
            sys.exit(1)
        
        tool = LoggerRollback(args.db_url, force=args.force)
        
        try:
            await tool.connect()
            
            if args.recent:
                # Parse hours
                hours_str = args.recent.lower().replace('h', '').replace('hour', '').replace('hours', '')
                try:
                    hours = float(hours_str)
                except ValueError:
                    print(f"[✘] Invalid time format: {args.recent}")
                    sys.exit(1)
                
                log_path = await tool.logger_recent(hours)
            else:
                log_path = await tool.logger_by_project(args.project, args.iteration)
            
            if log_path:
                sys.exit(0)
            else:
                sys.exit(1)
        
        finally:
            await tool.close()
    
    elif args.command == 'rollback':
        if not Path(args.log_file).exists():
            print(f"[✘] Log file not found: {args.log_file}")
            sys.exit(1)
        
        tool = LoggerRollback(args.db_url)
        
        try:
            if not args.dry_run:
                await tool.connect()
            
            success = await tool.rollback(args.log_file, args.dry_run)
            
            if success:
                print("\n[✓] Rollback completed successfully")
                sys.exit(0)
            else:
                print("\n[✘] Rollback failed or cancelled")
                sys.exit(1)
        
        finally:
            if not args.dry_run:
                await tool.close()


if __name__ == "__main__":
    asyncio.run(main())

