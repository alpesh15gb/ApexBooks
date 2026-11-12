# Reconstructed release readiness checkpoint

This is a scoped engineering checkpoint, not a delivery commitment or a declaration of comprehensive Indian accounting compliance.

## Highest priority remaining work

1. Integrate and independently review the later local corrections after published draft #59. Confirm the final exact commit, run CI on that commit, and reconcile the reconstructed stack against the earlier lost-fix inventory. Previously green CI on #59 does not validate subsequent changes.
2. Complete Windows/Android app builds and real UI acceptance. Portable C# client tests and the four Android CSV JVM tests now pass, closing the helper compilation gap. Native file picking, stale preview, double submit, session/company switching and device PDF workflows remain distinct acceptance tasks.
3. Finish the systematic feature/flow matrix using disposable synthetic books. Include financial scope/export consistency, keyboard nine-line entry, errors/focus/status, 320px reflow and large currency values. Local register visual browser checks are still blocked by socket permissions in this execution environment.
4. Verify release-specific backup and restore rehearsal, migrations, writer pause, rollback/recovery, smoke tests and version identity. No production systems have been inspected or altered in this batch. The user owns deployment.

## Delivery range

There is not yet sufficient evidence for a defensible calendar delivery range: the complete visual coverage matrix, native device outcomes and remaining reconstruction inventory are not closed, and each can reveal correctness work. Automated backend feedback has taken approximately two minutes per full local run, but that is not an estimate of remaining engineering or review time. Re-estimate after final-stack CI, independent review of known fixes and the first complete visual matrix pass.

A scoped release should explicitly list supported accounting/GST workflows and exclusions. Comprehensive Indian accounting compliance additionally depends on the entity, transactions, registrations and professional applicability review; software tests alone do not establish it.

## Isolated visual environment

The launcher /tmp/apex-visual-instance.py created /tmp/apex-visual-isolated-47ca5yyv with a disposable SQLite database and synthetic credentials/records. Initial web URL was http://127.0.0.1:59087 and API http://127.0.0.1:53837; command session 20847 remains open. Subsequent separate execution calls could not reach these loopback ports, so external/browser reachability is NOT confirmed. Do not infer that a URL valid inside one execution context is reachable in another. The launcher is available to run in the visual reviewer's execution context; it selects fresh ports and prints its access manifest. Production secrets are excluded by an explicit environment allowlist.
