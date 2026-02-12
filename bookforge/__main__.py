"""BookForge CLI - Main entry point"""
import argparse
import sys
from pathlib import Path

from .pipeline import Pipeline


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="BookForge - KDP Children's Book Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m bookforge run --idea "a brave little mouse"
  python -m bookforge run --idea "a magical garden" --age-group ages_5_7
  python -m bookforge run --idea "friends who help each other" --output ./my-book
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run the book creation pipeline")
    run_parser.add_argument(
        "--idea",
        required=True,
        help="The book idea/concept to develop"
    )
    run_parser.add_argument(
        "--age-group",
        default="ages_3_5",
        choices=["ages_0_3", "ages_3_5", "ages_5_7", "ages_7_9"],
        help="Target age group for the book (default: ages_3_5)"
    )
    run_parser.add_argument(
        "--output",
        default="bookforge/output",
        help="Output directory for generated files (default: bookforge/output)"
    )
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == "run":
        run_pipeline(args)
    else:
        parser.print_help()
        sys.exit(1)


def run_pipeline(args):
    """Run the book creation pipeline"""
    try:
        pipeline = Pipeline(output_dir=args.output)
        result = pipeline.run(idea=args.idea, age_group=args.age_group)
        
        print("\nPipeline completed successfully!")
        print(f"Report saved to: {result['text_report_path']}")
        print(f"\nCheck the output directory: {args.output}")
        
        # Display summary
        report_data = result.get("report_data", {})
        status = report_data.get("preflight_status", "UNKNOWN")
        
        if status == "PASSED":
            print("\n✓ All KDP preflight checks passed!")
            sys.exit(0)
        elif status == "WARNING":
            print("\n⚠ Pipeline completed with warnings. Check the report for details.")
            sys.exit(0)
        else:
            print("\n✗ Pipeline completed with errors. Check the report for details.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\nPipeline interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error running pipeline: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
