"""One Phase 2 command; the engineering pipeline and C field inference remain distinct."""
import argparse
import os
import sys
from phase2.workflow import (ROOT, add_algorithm_options, algorithm_mode, algorithm_command,
                             data_root, execute, fresh, install, verify_algorithm, write_status)


def main():
    p = argparse.ArgumentParser(description=__doc__, epilog='Engineering flags: --region, --start, --end, --from, --only, --method, --model, --no-plots. See python -m phase2.phase2_run --help.')
    p.add_argument('--demo', action='store_true', help='Isolated synthetic engineering fixture + offline C algorithm')
    p.add_argument('--engineering-only', action='store_true', help='Do not run the independent C workflow')
    p.add_argument('--algorithm-offline', action='store_true', help='Also run the offline C verification')
    add_algorithm_options(p)
    args, team_args = p.parse_known_args()
    mode = algorithm_mode(args)
    if args.demo and mode:
        p.error('--demo cannot be combined with real NASA/reviewed inputs; use phase2_test.py for both')
    if args.engineering_only and (mode or args.algorithm_offline):
        p.error('--engineering-only conflicts with algorithm options')
    # Validate original CLI arguments before starting any work.
    allowed = {'--from','--only','--region','--start','--end','--method','--model','--no-plots'}
    if any(x.startswith('--') and x.split('=')[0] not in allowed for x in team_args):
        p.error('unknown engineering argument: ' + ' '.join(team_args))
    if args.demo and ('--from' in team_args or '--only' in team_args):
        p.error('demo starts with a new database; use the original module for partial reruns')
    run = fresh(data_root() / ('demo/phase2_runs' if args.demo else 'phase2/runs'))
    if install(args):
        return write_status(run, {'dependency_install': 1})
    env = os.environ.copy()
    stages = {}
    if args.demo:
        env['PARSEC_DATA_DIR'] = str(run / 'workspace')
        stages['synthetic_seed'] = execute([sys.executable, '-m', 'phase2.demo'], env=env)
        if stages['synthetic_seed']:
            return write_status(run, stages)
    stages['engineering'] = execute([sys.executable, '-m', 'phase2.phase2_run', *(['--demo'] if args.demo else []), *team_args], env=env)
    if stages['engineering']:
        return write_status(run, stages)
    if not args.engineering_only and (args.demo or args.algorithm_offline or mode):
        verify_algorithm()
        if args.demo or args.algorithm_offline:
            stages['algorithm_offline'] = execute(algorithm_command('offline', args, run / 'algorithm'))
        if mode and not stages.get('algorithm_offline', 0):
            stages['algorithm_' + mode] = execute(algorithm_command(mode, args, run / 'algorithm'))
    else:
        print('Engineering baseline only: use --nasa-csv-dir / --reviewed-data or --algorithm-offline to run the C workflow.')
    return write_status(run, stages)


if __name__ == '__main__':
    sys.exit(main())
