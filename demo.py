#!/usr/bin/env python3
"""
Demo script for BookForge pipeline
Shows example usage with different book ideas
"""

import sys
import os

# Add parent directory to path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bookforge.pipeline import Pipeline


def demo_basic():
    """Basic demo with simple idea"""
    print("=" * 60)
    print("DEMO 1: Basic Usage")
    print("=" * 60)
    
    pipeline = Pipeline(output_dir="demo_output/basic")
    result = pipeline.run(
        idea="a curious cat exploring the city",
        age_group="ages_3_5"
    )
    
    print(f"\nGenerated: {result['report_data']['story_title']}")
    print(f"Status: {result['report_data']['preflight_status']}")
    

def demo_different_ages():
    """Demo with different age groups"""
    print("\n" + "=" * 60)
    print("DEMO 2: Different Age Groups")
    print("=" * 60)
    
    ideas_and_ages = [
        ("baby animals learning colors", "ages_0_3"),
        ("friends building a treehouse", "ages_5_7"),
        ("a young inventor's first robot", "ages_7_9"),
    ]
    
    for idea, age_group in ideas_and_ages:
        print(f"\n--- Creating book for {age_group} ---")
        pipeline = Pipeline(output_dir=f"demo_output/{age_group}")
        result = pipeline.run(idea=idea, age_group=age_group)
        print(f"✓ Created: {result['report_data']['story_title']}")


def main():
    """Run demos"""
    print("BookForge Pipeline Demo")
    print("=" * 60)
    print("This demo shows how to use the BookForge pipeline")
    print("to create KDP-ready children's books\n")
    
    try:
        demo_basic()
        
        # Uncomment to run more demos
        # demo_different_ages()
        
        print("\n" + "=" * 60)
        print("Demo completed! Check the demo_output/ directory")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError in demo: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
