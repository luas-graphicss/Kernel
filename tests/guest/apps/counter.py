from kernel_apps import runtime

state = {"runs": 0}


def main() -> bool:
    state["runs"] += 1
    print(f"counter: runs={state['runs']} arguments={len(runtime.current().arguments) - 1}")
    return True
