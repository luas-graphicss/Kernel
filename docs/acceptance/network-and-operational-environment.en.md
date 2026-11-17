# Acceptance record: network and operational environment

[Português](network-and-operational-environment.md)

Results of a complete verification run on the tree introducing IPv4 networking, sockets, the system manager, shell and applications. Numbers come from reports written to `build/qemu-riscv64/reports/`. Unmeasured claims are not included.

This is a historical record for the images below, not the current release. Current evidence is in [Qualification and distribution](qualification-and-distribution.en.md).

## Execution

| Item | Value |
| --- | --- |
| Date | November 16, 2026, 22:55–22:59 UTC |
| Tree | `feat/network-and-operational-environment`, based on `main` commit `155ac06` |
| Host | Linux 6.18.56 x86_64, two 2.9 GHz Intel Xeon vCPUs, 4 GiB RAM |
| Guest | QEMU 9.2.4 TCG, one hart, 256 MiB, `qemu-riscv64` |
| Network peer | Host Linux 6.18.56 TCP/IP stack in a network namespace with no external route |
| Build | Empty directory, hash-verified `toolchain.lock.toml` tools |

Commands followed CI workflow order, with none skipped. All 26 stages returned 0 in 274 s.

| Stage | Result |
| --- | --- |
| `ruff format --check .` | 606 files, none needing formatting |
| `ruff check .` | No findings |
| `mypy --strict host src` | 306 files, no errors |
| `pytest tests/host tests/conformance` | 873 passed |
| `kernel-tool toolchain` | GCC 15.2.0-1, QEMU 9.2.4-1, MicroPython 1.29.0 verified |
| `kernel-tool native-check` | 11 hosted native tests under sanitizers and static analysis |
| `kernel-tool build` | Images generated in 33 s |
| `kernel-tool test`, 14 suites | 41/41 scenarios |
| `kernel-tool fault-test`, 3 suites | 3/3 scenarios and four host stages |
| `kernel-tool verify-filesystem --corpus tests/faults/storage` | Expected verdict for all 21 images |
| `kernel-tool verify-artifacts --reproduce` | Second build in another directory produced identical images |

## Tested images

| Image | Bytes | SHA-256 |
| --- | --- | --- |
| `kernel.elf` | 1,635,424 | `cc09636d934a288b365569f2deb9f03d84129f8fc7754ca442c22a31dee0dea0` |
| `kernel-selftest.elf` | 1,732,968 | `4e9f8529383f2db73b42411bd0d4b8b96b2c3da9214b81a88726fecd1ac60902` |
| `init.img` | 431,655 | `3d6b481c9238f76df368e76c04cada0efe3c8180f7191367bcc73e3488aad0a7` |
| `tests.img` | 622,799 | `6ac6f235dac4fc45a9b490d60d7fa6693e31619b347259a5c2a832572668df61` |
| `boot.img` | 65,536 | `f03917e4348677b13968d9da6ab95fc3fbc22bc59c7285d6c8ebd5cf5a354412` |

Every run's `artifacts.json` contains the same fields for comparison.

## QEMU suites

| Suite | Scenarios passed | Cases | Checks | QEMU time |
| --- | --- | --- | --- | --- |
| `bootstrap` | 9/9 | 0 | 0 | 41.0 s |
| `memory` | 1/1 | 7 | 78 | 0.6 s |
| `processes` | 3/3 | 7 | 160 | 65.1 s |
| `capabilities` | 1/1 | 6 | 47 | 0.2 s |
| `ipc` | 1/1 | 9 | 83 | 0.6 s |
| `scheduling` | 2/2 | 7 | 37 | 1.4 s |
| `devices` | 3/3 | 11 | 91 | 0.9 s |
| `vfs` | 1/1 | 7 | 71 | 1.6 s |
| `storage` | 8/8 | 3 | 14 | 5.3 s |
| `network` | 1/1 | 7 | 71 | 13.1 s |
| `network-interop` | 2/2 | 14 | 14 | 7.5 s |
| `applications` | 1/1 | 0 | 0 | 5.0 s |
| `supervision` | 6/6 | 5 | 32 | 3.6 s |
| `system-journey` | 2/2 | 0 | 0 | 4.2 s |
| `device-reset` | 1/1 | 4 | 21 | 7.2 s |
| `storage-crash` | 1/1 | 0 | 0 | 0.8 s |
| `network-faults` | 1/1 | 5 | 26 | 2.6 s |
| Total | 44/44 | 92 | 745 | 160.5 s |

A case is a transcript line `test: suite=... case=... checks=N result=ok`; N counts guest-side assertions. Scenarios without cases are checked by `kernel-tool` against required and forbidden transcript lines.

The nine preexisting suites, `device-reset`, `storage-crash`, volume corpus and image reproduction passed in the same run on the same tree.

## Networking against the peer

### `network`

One boot, 13.1 s.

| Case | Checks |
| --- | --- |
| `interface-and-echo` | 10 |
| `datagrams` | 13 |
| `streams` | 15 |
| `listening` | 7 |
| `deadlines-cancellation-and-backpressure` | 8 |
| `socket-quota` | 5 |
| `access-rights` | 13 |

The 20,480-byte upload reached the peer with SHA-256 `6c6d0a81798e4cd4515a9862dcaf81a08c83e7e6b5b85bac3177fd69ee8e082a`. A peer-initiated connection returned 16,384 identical bytes with SHA-256 `42bb8d620d204120a5b6676bd04868478eef3647bb22d6eec4e6830ca72c11d0`.

### `network-interop`

Two boots with the same seven cases: `interop-clean-link` in 2.5 s and `interop-impaired-link` in 5.0 s, with 3% loss, 2% duplication and 10% reordering from seed 7. Transfer data uses fixed seeds, receivers calculate hashes and `kernel-tool` checks them. Both links produced the same values.

| Case | Bytes | Verification |
| --- | --- | --- |
| `upload-verified-by-the-peer` | 131,072 | SHA-256 `fd3151cf480b2df6a75c3e5e5e75d037c13fa3105a9c367b7f8642e63f009b7c` |
| `download-verified-by-checksum` | 131,072 | CRC-32 `862839fd` |
| `relay-through-the-guest` | 65,536 | SHA-256 `194a75d0303b675a20876910e727ddb778de719ac1786232f1ab1b9b621e3d10` |
| `inbound-connection` | 65,536 | SHA-256 `aae5ad71c082c551f0778f33b9d30ded11136d2becabb1e626d1b588a54a4049` |
| `fragmented-datagrams` | Four 3072-byte datagrams | All delivered whole |
| `slow-reader` | 32,768 | SHA-256 `bcc4256d1bd2c78edf1321ffd51a4dd43f4799b30f6977d1cd98931779c6e3fb` |
| `buffers-returned` | 0 | No buffered bytes after transfers |

The impaired station dropped 19 frames toward the guest and 22 toward the peer. The guest retransmitted 42 segments and received 61 out of order. Both counters were zero on the clean link.

### `network-faults`

One 2.6 s boot and a host-side stage verifying injected traffic.

| Case | Checks | Outcome |
| --- | --- | --- |
| `malformed-traffic` | 4 | 31 specimens in 32 frames, counted by their layer parsers. No sockets or buffers retained; echo worked afterward |
| `connection-flood` | 6 | 32 forged connection requests against backlog 4. Excess counted and rejected; none reached the application. A real peer then connected: 8192 bytes, SHA-256 `d197b0c12fff2c87d994e76373edd4cf7f4b204692aeb6d331718f6c0cca46a8` |
| `link-blackout` | 4 | 1.5 s outage during transfer; 7 frames lost toward peer, retransmission completed transfer |
| `device-reset` | 4 | `network: link=down`, `network: device=recovered resets=1`, `network: link=up`, then successful echo |
| `service-restart-with-a-waiting-client` | 8 | Waiter notified, old sessions rejected by the new instance, peer reachable |

| Parser | Specimens | Counters |
| --- | --- | --- |
| Ethernet | 2 | `frames-malformed` |
| ARP | 5 | `arp-malformed` |
| IPv4 | 6 | `ipv4-malformed`, `ipv4-bad-checksum`, `ipv4-options-refused` |
| Fragments | 3 | `fragments-invalid` |
| ICMP | 3 | `icmp-malformed` |
| UDP | 5 | `udp-malformed`, `udp-bad-checksum` |
| TCP | 7 | `tcp-malformed`, `tcp-bad-checksum` |

### Captures

Captures record the guest interface's view: every outgoing frame and every frame delivered to it. Forged frames count as guest deliveries.

| Capture | Frames | To guest | To peer | Lost toward guest | Lost toward peer | Forged |
| --- | --- | --- | --- | --- | --- | --- |
| `network-cases.pcap` | 286 | 107 | 179 | 0 | 0 | 0 |
| `interop-clean-link.pcap` | 991 | 422 | 569 | 0 | 0 | 0 |
| `interop-impaired-link.pcap` | 1145 | 507 | 627 | 19 | 22 | 0 |
| `applications.pcap` | 0 | 0 | 0 | 0 | 0 | 0 |
| `journey-first-boot.pcap` | 29 | 13 | 16 | 0 | 0 | 0 |
| `journey-second-boot.pcap` | 0 | 0 | 0 | 0 | 0 | 0 |
| `network-faults.pcap` | 157 | 100 | 50 | 0 | 7 | 64 |

Frames are truncated to 96 bytes. Captures contain only test addresses in `10.0.2.0/24` and generated data; host traffic never traverses the station, so nothing required redaction. CI attaches run captures under `reports/captures/`, with their hashes in suite reports.

## Applications, supervision and system journey

### `applications`

One 5.0 s boot, with 28 shell commands: 24 `status=ok` and four expected rejections.

| Situation | Transcript |
| --- | --- |
| Arguments delivered, no prior-run memory | `counter: runs=1 arguments=2`, then `counter: runs=1 arguments=0` |
| Policy capabilities only | `authority: capabilities=5 send-only-endpoints=1 administration=refused shell-modules=0 files=read-write network=granted` |
| Exception, syntax error, absent file | `system: application=N state=exited reason=exit value=1` for each |
| Noncooperative loop | `wait 7 1` returns `TIMED_OUT`; `kill 7` produces `reason=killed` |
| Heap exhaustion | `system: application=8 state=exited reason=exit value=1`; shell remains usable |
| Application limit | Four running; fifth rejected with `LIMIT_EXCEEDED` |
| Shutdown with applications | `system: shutdown=applications stopped=4`, `system: shutdown=complete clean=1` |

### `supervision`

| `supervision-cases` case | Checks |
| --- | --- |
| `dependency-order` | 6 |
| `readiness-and-degraded-state` | 7 |
| `restart-with-a-pending-request` | 8 |
| `restart-budget` | 6 |
| `restart-window` | 5 |

In `network-absent`, network exhausted three attempts and reported `state=degraded restarts=3 window-seconds=60`. The system continued degraded: `ps` and `ls` worked; `net` returned `BAD_STATE`.

The four invalid configurations ended with `kernel: status=failed` and no service started:

| Scenario | Rejection line |
| --- | --- |
| `configuration-missing` | `system: configuration=rejected reason=missing-document subject=boot/system/config` |
| `configuration-circular` | `system: configuration=rejected reason=dependency-cycle subject=console` |
| `configuration-excessive` | `system: configuration=rejected reason=out-of-range subject=service.network.heap_bytes` |
| `configuration-inconsistent` | `system: configuration=rejected reason=gateway-off-link subject=interface.gateway` |

### `system-journey`

Two boots share one data volume.

The first took 3.7 s and ran 28 commands. Twenty-four returned `status=ok`; three expected failures were `cat` of a missing file (`NOT_FOUND`), `rm` on the boot image (`READ_ONLY`) and `wait` for an application blocked on a connection (`TIMED_OUT`). The final command was `shutdown restart`. `fetch.py` wrote 6240 TCP-received bytes to `data/journey/greeting`; `wordcount.py` reported `lines=240 words=1200 bytes=6240`. `sync` returned `durable=1` for both writable volumes. Shutdown killed the blocked application, stopped all five services in reverse order with `clean=1` and ended with `kernel: power=restart`.

The second took 0.6 s and ran seven successful commands. The pre-restart note retained its 27 bytes; the downloaded file again produced `lines=240 words=1200 bytes=6240`; shutdown ended with `kernel: status=ok`.

## Acceptance criteria

| Criterion | Evidence from this execution |
| --- | --- |
| Protocols work with a real external peer within the documented profile | `network`, 71 checks, and clean-link `network-interop`, against Linux 6.18.56 |
| Bidirectional transfers preserve content under loss and reordering | Impaired-link hashes match clean-link hashes despite 41 dropped frames |
| Bounded parsers/reassembly; malformed traffic cannot stop service/kernel | `network-faults/malformed-traffic`; malformed-input and reassembly conformance tests |
| A peer or process cannot exhaust global resources | Socket quota, deadlines/backpressure, connection flood, slow-reader and returned-buffer cases |
| Shell launches, observes, kills and waits for isolated applications | `applications` |
| Every shell command performs a real operation and returns status | All 15 commands exercised in a passing scenario, required by `tests/conformance/test_api_conformance.py` |
| Supervision enforces dependencies, restart limits and least authority | `supervision`, 32 checks, plus `network-absent` |
| Complete boot/program/file/network/sync/shutdown/restart journey | Both `system-journey` boots |
| Every public interface has status and evidence | `docs/architecture/api-conformance.en.md`, checked against code by the same test |
| Earlier suites still pass | The 11 preexisting suite rows, volume corpus and image reproduction |

## Failure found before this execution

An earlier complete run failed `service-restart-with-a-waiting-client` in `network-faults`: two connections remained where one was expected. The capture showed that the accepted connection from `connection-flood` was still closing when the next case blacked out the link. Its FIN was lost and awaited retransmission. TCP behaved correctly; case ordering was wrong. `connection-flood` and `link-blackout` now wait for zero connections before finishing.

After the fix and before this recorded execution, `network-faults` passed ten consecutive runs; `network`, `network-interop`, `applications`, `supervision` and `system-journey` each passed three runs.

## Failure found after this execution

The first PR CI run failed `network/interface-and-echo` at `an echo that gets no answer ends at its deadline`: echo to off-subnet `192.0.2.1` ended before its deadline. The other six cases and sixteen earlier stages passed; nine later stages did not run.

The difference was in the host. New network namespaces inherit host IPv4 forwarding. With forwarding enabled, the peer replies to off-subnet traffic with network-unreachable ICMP instead of dropping it, completing echo early. This execution's host had forwarding disabled; enabling it reproduced the runner failure.

The station now disables forwarding inside the namespace before creating its interface. Three host tests cover this host-tool-only fix; guest images are unchanged. Subsequent runs on these images:

| Host forwarding | Checks | Result |
| --- | --- | --- |
| Enabled | `network`, `network-interop`, `applications`, `system-journey`, `network-faults` | 7/7 scenarios |
| Disabled | `network` | 1/1 scenario |
| Disabled | Formatting, lint, strict types, host/conformance tests | No findings; 876 passed |

Other tables retain the original execution's 873-test count.

## Outside this record

- Timings are from one host and TCG, not physical hardware.
- Interoperability covers only Linux 6.18.56 TCP/IP.
- Parser fuzzing was still open at this milestone under R-19 in `docs/architecture/requirements.en.md`; later qualification evidence is recorded separately.
- CI results on `ubuntu-24.04` are in the pull request, not this record.
