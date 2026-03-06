#!/usr/bin/env python3
"""Universal token generator for all supported brokers."""
import argparse, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--broker", required=True, choices=["upstox","zerodha","angelone","fyers"])
    args = parser.parse_args()
    if args.broker == "upstox":
        from scripts.upstox_login import main as upstox_main
        upstox_main()
    else:
        print(f"Token generation for {args.broker} not yet implemented.")
        print("Please refer to the broker's official SDK documentation.")

if __name__ == "__main__":
    main()
