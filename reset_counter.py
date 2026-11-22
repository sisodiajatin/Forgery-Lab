"""Clear the live humans-vs-detector counter (run before a demo).  python reset_counter.py"""
import modal

state = modal.Dict.from_name("forgery-lab-state", create_if_missing=True)
keys = [k for k in state.keys() if k.startswith("human:")]
for k in keys:
    state.pop(k)
print(f"cleared {len(keys)} human result(s)")
