from kernel_tool.faults.stages import Stage
from kernel_tool.network.malformed import specimens
from kernel_tool.scenarios.network_suites import FLOOD_REQUESTS, INTRUDER

INJECTED_TRAFFIC = "injected-traffic"


def injection_stage() -> Stage:
    injected = specimens(INTRUDER)
    counts = {
        "specimens": len(injected),
        "frames": sum(len(specimen.frames) for specimen in injected),
        "parsers": len({specimen.parser for specimen in injected}),
        "connection-requests": FLOOD_REQUESTS,
    }
    evidence = [
        {
            "name": specimen.name,
            "parser": specimen.parser,
            "counter": specimen.counter,
            "frames": len(specimen.frames),
        }
        for specimen in injected
    ]
    return Stage(INJECTED_TRAFFIC, counts, (), evidence)
