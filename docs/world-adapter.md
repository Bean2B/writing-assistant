# World actor decision adapter

Use the adapter to exercise a character's offered choices on a specific World Sandbox branch and revision. The world engine owns narrative time, effects, actor knowledge and settlement. The adapter owns the selected transport, a durable attempt and its validation status.

```sh
wa=./scripts/writing-assistant
book='books/创作作品/渡灯'
"$wa" --book "$book" world-adapter --run estuary prepare crossing --actor boatman --expect 0
"$wa" --book "$book" world-adapter --run estuary execute crossing --expected-plan-sha256 DIGEST
"$wa" --book "$book" world-adapter --run estuary settle crossing --expected-plan-sha256 DIGEST
```

The default offline choice is the lexicographically first offered key. This provides a repeatable state-machine rehearsal. For a trusted local decision program, supply `--runner /path/to/adapter` at preparation and execution. The executable must match the prepared digest. It receives only the actor projection, offered keys and labels, and a random attempt identity over UTF-8 JSON stdin. The request shape is `{"format":"writing-assistant/actor-decision/1","attempt":"…","actor_view":{…},"actions":{…}}`. The response on stdout must contain exactly `format` equal to `writing-assistant/actor-choice/1`, the same `attempt`, and one offered `choice` key.

The process has a private temporary working directory and receives a small environment for local execution. This route supplies no network client or provider credentials. As with other local executables, filesystem and network access permissions are governed by the OS. Trusted programs provided by the user must suit the intended environment.

`inspect` shows the adapter and world stages. After dispatch begins, a second execute never sends the turn again. If the coordinator exits, `recover ID --expected-plan-sha256 DIGEST` waits for the surviving local worker to finish by refusing recovery while its lock is held. After it exits, recovery can validate an atomic result file and record the choice. The built-in choice is deterministic and recoverable from the frozen offer. A missing, invalid or unoffered local result leaves the adapter `uncertain` and the world decision unsettled. Execute and recover return status 2 with the original structured outcome. The owner can inspect the original attempt. Independent evidence is required for a manual world result. Settlement applies authored consequences once and is retryable.

To run the isolated checks, use `python3 -m unittest discover -s tests -p test_world_adapter.py -v`. The tests exercise projection privacy, an unwanted choice, owner interruption, fresh-process recovery and idempotent settlement on synthetic worlds. A model's choice quality or suitability for a live provider requires separate evaluation.
