"""reg-lab-report — lectern Layer 3.

Two subcommands:
  render   read-only instructor REPORT.md from the recon bundle + digest cohort
  deliver  signed feedback-branch delivery (dry-run by default)
"""
import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("render", "deliver"):
        print("usage: reg-lab-report {render|deliver} ...", file=sys.stderr)
        raise SystemExit(2)
    sub, rest = argv[0], argv[1:]
    if sub == "render":
        from lectern import report_render
        return report_render.main(rest)
    from lectern import feedback_deliver
    return feedback_deliver.main(rest)


if __name__ == "__main__":
    raise SystemExit(main())
