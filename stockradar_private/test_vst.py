
from scanner import fetch, analyze

print("Testing VST weekly support and resistance...")

result = analyze("VST", fetch("VST"))

if result is None:
    print("No analysis result available.")
else:
    print("Ticker:", result["ticker"])
    print("Close:", result["close"])
    print("Support:", result["support"])
    print("Resistance:", result["resistance"])
    print("Signal:", result["signal"])
    print("Distance to resistance:", result["resistance_distance_pct"])
