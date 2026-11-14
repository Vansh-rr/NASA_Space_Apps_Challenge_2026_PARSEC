"""One independent command to test Phase 2 engineering and the unchanged C algorithm."""
import argparse
import sys
from phase2.workflow import (ROOT, add_algorithm_options, algorithm_mode, algorithm_command,
                             data_root, execute, fresh, install, verify_algorithm, write_status)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    scope = p.add_mutually_exclusive_group()
    scope.add_argument('--engineering-only', action='store_true')
    scope.add_argument('--algorithm-only', action='store_true')
    add_algorithm_options(p)
    args = p.parse_args()
    mode = algorithm_mode(args)
    if args.engineering_only and mode:
        p.error('NASA/reviewed inputs require the algorithm test')
    run = fresh(data_root() / 'test_runs')
    if install(args, engineering=not args.algorithm_only):
        return write_status(run, {'dependency_install': 1})
    stages = {}
    if not args.algorithm_only:
        stages['engineering_tests'] = execute([sys.executable, '-m', 'pytest', 'tests_phase2', '-q'])
    if not args.engineering_only:
        verify_algorithm()
        stages['algorithm_offline'] = execute(algorithm_command('offline', args, run / 'algorithm'))
        if mode and not stages['algorithm_offline']:
            stages['algorithm_' + mode] = execute(algorithm_command(mode, args, run / 'algorithm'))
    return write_status(run, stages)


if __name__ == '__main__':
    sys.exit(main())

