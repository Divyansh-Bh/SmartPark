class Process:
    def __init__(self, pid, burst_time, arrival_time=0):
        self.pid = pid
        self.burst_time = burst_time
        self.arrival_time = arrival_time
        self.completion_time = 0
        self.turnaround_time = 0
        self.waiting_time = 0

def simulate_fcfs(processes):
    # Sort processes by Arrival Time (FCFS invariant)
    sorted_proc = sorted(processes, key=lambda p: p.arrival_time)
    
    current_time = 0
    gantt_chart = []

    for p in sorted_proc:
        # If CPU is idle until the process arrives
        if current_time < p.arrival_time:
            gantt_chart.append(("IDLE", current_time, p.arrival_time))
            current_time = p.arrival_time

        start_time = current_time
        current_time += p.burst_time
        p.completion_time = current_time
        p.turnaround_time = p.completion_time - p.arrival_time
        p.waiting_time = p.turnaround_time - p.burst_time
        gantt_chart.append((p.pid, start_time, current_time))

    total_wt = sum(p.waiting_time for p in sorted_proc)
    total_tat = sum(p.turnaround_time for p in sorted_proc)
    n = len(sorted_proc)
    
    avg_wt = total_wt / n if n > 0 else 0
    avg_tat = total_tat / n if n > 0 else 0

    return {
        "processes": sorted_proc,
        "gantt_chart": gantt_chart,
        "avg_waiting_time": round(avg_wt, 2),
        "avg_turnaround_time": round(avg_tat, 2)
    }

def print_simulation_results(result):
    """
    Renders simulation results in a neat console table with a Gantt chart.
    """
    print("\n" + "=" * 65)
    print("      OPERATING SYSTEMS LAB: FCFS CPU SCHEDULING SIMULATION")
    print("=" * 65)
    print(f"{'PID':<6} | {'Arrival':<8} | {'Burst':<6} | {'Completion':<10} | {'Turnaround':<10} | {'Waiting':<8}")
    print("-" * 65)

    for p in result["processes"]:
        print(f"{p.pid:<6} | {p.arrival_time:<8} | {p.burst_time:<6} | {p.completion_time:<10} | {p.turnaround_time:<10} | {p.waiting_time:<8}")

    print("-" * 65)
    print(f"Average Waiting Time    : {result['avg_waiting_time']} ms")
    print(f"Average Turnaround Time : {result['avg_turnaround_time']} ms")
    print("=" * 65)

    # Render Gantt Chart
    print("\n--- Visual Gantt Chart ---")
    bar = "|"
    timeline = "0"
    for pid, start, end in result["gantt_chart"]:
        bar += f"  {pid}  |"
        timeline += f"{end:>{len(pid) + 5}}"
    print(bar)
    print(timeline)
    print("=" * 65 + "\n")

if __name__ == "__main__":
    # Test case matching standard university exam question:
    # Processes P1, P2, P3 with burst times 5, 3, 2 (all arriving at time 0)
    sample_processes = [
        Process(pid="P1", burst_time=5, arrival_time=0),
        Process(pid="P2", burst_time=3, arrival_time=0),
        Process(pid="P3", burst_time=2, arrival_time=0),
    ]

    print("[OS Simulation] Executing standard sample test case:")
    results = simulate_fcfs(sample_processes)
    print_simulation_results(results)
