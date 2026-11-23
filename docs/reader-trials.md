# Continuous and comparative reader trials

Use the same book for ordinary writing and experimental drafts. Save each new version in that book. A new comparison uses a new trial ID within it. Preserve historical panels and reading order as originally observed.

With a book selected, register each original reader's actual host session using `reader NAME --handle HANDLE`. Create a plan by naming the same readers and listing every exact chapter revision in the desired order:

```sh
wa=./scripts/writing-assistant
"$wa" --book "$book" trial create opening --reader 人物读者 --reader 行动读者 --reader 氛围读者 \
    --item first/1:1 --item first/2:1 --item second/1:2 --item second/2:2
```

Each named comparison arm retains chronological chapters. Every reader receives the same overall order. The coordinator keeps the arm, revision and author intent private. A simple continuous read can omit the arm label, e.g. `--item 1:1 --item 2:1`.

For each reader use `trial next opening --reader NAME`. The handle, digest, packet id and ordinal are coordinator fields. Forward only the decoded text and the same neutral question to the recorded actual session. A repeated call returns the same pending packet. After receiving the original response use `trial respond opening --reader NAME --packet ID --sha256 DIGEST --file REPLY`. Include `--stop` only when the reader chose to stop. Keep their wording about where and why in the response. Other readers can continue at their own pace.

`trial progress opening` shows counts and stopping points. Once everyone has finished or stopped, `trial results opening` returns each original reply with its manuscript identity. Save the coordinator's judgment using `trial evaluate opening --file EVALUATION`. A trial with `--historical` on creation draws exclusively from archived book responses on the specified revisions. Its presentation order follows the supplied plan. Original session delivery order and stops remain unverified. A fresh trial keeps its own packets and responses even when the book already contains historical or ordinary feedback for that revision.

To adopt a manuscript from an evaluated trial, the coordinator forwards the explicit user decision through `trial adopt opening --user-event EVENT.json`. The JSON object contains `event_id`, `actor_role` set to `user`, `action` set to `adopt-chapter`, the trial's `run_key`, and exact `chapter`, `revision` and `sha256`. The trusted caller can use `trials.adopt_user_event` directly. The CLI checks event structure, target and replay identity. The host authenticates the user and must supply the actual event. A local file or caller-provided role string cannot establish who spoke. Reader preference and the coordinator's evaluation never adopt a chapter on their own.
