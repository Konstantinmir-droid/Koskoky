import sys
if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        from localdoc.selftest import run
        raise SystemExit(run(sys.argv[2]))
    from localdoc.gui import main
    raise SystemExit(main())
