# The Other Side of Yesterday
## Chapters 1–2: playable dialogue and narrative implementation brief

**Status:** Proposed production draft. New dialogue, the canvas quest, the archive consequence, and the return-clock rule are proposals, not claims about already implemented content. Preserve approved project scripts where they conflict and record the conflict before replacing anything.

**Scope:** One compact playable opening on Verdant: the half-ruined family house and courtyard gate in the present; the same neighborhood, clinic, and harbor in the past. This intentionally keeps the latest house/city designs in one location rather than introducing another island in the opening. Other islands and later endings are unchanged.

**For Codex:** Implement the authored dialogue below using the existing Unreal project and dialogue/quest systems. Do not migrate engines, invent plugin APIs, create duplicate NPCs, or replace dialogue with live-generated text. Do not claim that writing this script or source code means it has been imported, voiced, animated, or playtested.

---

## 1. Continuity rules

1. The playable present is approximately twenty years after the war. The protagonist's five years of preparation occur within that period, not twenty years plus another five years after the playable opening.
2. Start with three brief, skippable recollections across those five years, then enter the playable present. Skipping the recollections does not remove quest flags or clues.
3. The protagonist has not knowingly met his father as an adult. The accessible family photograph shows Mother holding the protagonist as a baby; his father took the photograph and is not in it. Do not invent a damaged face or convenient amnesia to hide the revelation.
4. The healer is Elias in writer-only notes, but his player-facing name in these chapters is **Healer**. Do not expose his name or relationship in subtitles, journals, menus, save-slot descriptions, achievements, or ordinary debug overlays.
5. Mother does not knowingly disclose the healer's identity. Do not have her describe his face, distinctive clothing, or medical role in these scenes.
6. The watch preserves the traveler's memory of the previous history. Other residents remember the current history. Establish this through a small observable discrepancy, not a lecture.
7. Proposed return-clock rule: an active excursion has a return signal whose present-day clock advances while the protagonist is away. Returning does not put him beside an earlier copy of himself. The same person's excursion is not freely replayable.
8. Time travel is anchored, not unrestricted date selection. An established choice remains committed on return trips; visiting the past does not silently reset it.
9. The first choice makes one community shelter usable during a storm, allowing a historical record to be created there. It does not automatically prevent the war, rebuild the city, resurrect the father, or guarantee that everyone survived.
10. Characters speak naturally. Small pauses and actions carry emotion; do not add a musical swell or a speech to every interaction.
11. The Chronowatch displays status information. It has no speaking AI personality in this draft.
12. Trust is not affection purchased by choosing the nicest-sounding line. Honesty and uncertainty are not penalized. Major relationship changes come from actual follow-through.

## 2. Cast and presentation

- **Protagonist:** Player-controlled young inventor. No new permanent name or exact age is assigned here. Spoken choices belong to the player; do not speak an unselected response.
- **Mother:** Warm, tired, practical, capable of humor. She has her own concerns and is not just a tutorial guide.
- **Healer:** Quietly capable and attentive. He is busy helping people, not waiting to deliver a monologue.
- **Sela:** Storekeeper. Direct, observant, and generous within the limits of her supplies.
- **Neri:** Young local resident. Curious and a little impatient, not a vehicle for constant jokes or exposition.

Use subtitles even without recorded audio. Stage directions are instructions, not subtitle text. A minimum hold time and manual advance should keep subtitle-only playback readable. Add no fake lip sync when audio/timing data is absent.

Use IDs below as stable content identifiers. The flags are conceptual content requirements, not assertions about a built-in Unreal dialogue format.

---

# CHAPTER 1 — THE FUTURE SHE REMEMBERED

## C1_00 — Fragments across five years

**Trigger:** New Game, once. Skippable.
**Staging:** Brief object-centered recollections with clear time labels. Do not force head movement in VR. An early watch sketch becomes a partial mechanism, then the nearly finished device. Mother shares memories across the years.

### Five years earlier

**Protagonist:** "What did the town sound like?"

**Mother:** "Before the war?"

**Protagonist:** "Before everyone stopped talking about it."

**Mother:** "Bells. Boats. People arguing over the price of fish."

*[A small smile.]*

**Mother:** "I used to wish it was quieter."

### Three years earlier

**Protagonist:** "Was there a moment when someone could have stopped it?"

**Mother:** "There were a lot of moments. We just didn't know which ones mattered."

**Protagonist:** "Someone must have known."

**Mother:** "Perhaps. The people who survived didn't all tell the same story."

### One year earlier

*[A spring jumps loose on the workbench.]*

**Protagonist:** "That was supposed to stay there."

**Mother:** "You said that about the last one."

**Protagonist:** "The last one hit the ceiling. This is progress."

*[She sets down a bowl beside him.]*

**Mother:** "Then celebrate with something warm."

**Transition:** Present day. Player control begins in the surviving part of the house.

**Journal objective:** "Before the final test: examine the photograph and letter, then speak with Mother."

## C1_01 — The photograph

**Trigger:** First inspection of the family photograph. The image shows Mother and a baby, not the father.

**Protagonist:** "You look tired."

**Mother:** "You were six weeks old. I was tired."

**Protagonist:** "Who took it?"

**Mother:** "Your father. He tried three times. You cried through all of them."

**Protagonist:** "He kept this one?"

**Mother:** "He said we looked like ourselves."

*[Let the player turn the photograph over.]*

**Writing on the back:** "Our first summer at home."

**Effect:** Set `PHOTO_READ` once. Repeat inspections show the object and writing without replaying the whole exchange.

## C1_02 — The unsent letter

**Trigger:** First inspection of the folded letter. It is Mother's unsent letter, not a document revealing the healer's identity.

**Letter text:**

> The upstairs room still leaks when the wind comes from the sea.
>
> He says he can mend it. He says that about everything now.
>
> I kept your chair. Not because I think a chair can bring someone home. I just wasn't ready to give it away.
>
> I don't know where to send this.

**Protagonist:** "You never sent it."

**Mother:** "I never found an address."

**Protagonist:** "Do you want me to put it away?"

**Mother:** "Leave it there for now."

**Effect:** Set `LETTER_READ` once. Preserve the object; reading it does not consume it.

## C1_03 — Optional early conversation

**Condition:** Player talks to Mother before both opening objects have been inspected.

**Mother:** "You're very quiet this morning."

**Protagonist:** "I'm trying not to think too far ahead."

**Mother:** "Then stay here for a minute. I'll make some tea."

**Behavior:** Allow departure without a penalty. Do not start the final departure dialogue yet. Keep the current objective visible without Mother repeatedly naming quest objects.

## C1_04 — Mother: the final test

**Condition:** `PHOTO_READ` and `LETTER_READ`; workbench departure conversation not completed.
**Staging:** Mother sits or finishes a small household task. Player camera remains free.

**Mother:** "You cleaned the workbench."

**Protagonist:** "I needed to find things."

**Mother:** "You need to find things every day."

*[She looks at the watch.]*

**Mother:** "You're going to try it."

### Choice A — "I think I can stop what happened."

**Protagonist:** "I think I can stop what happened."

**Mother:** "You know what the war left behind. You don't yet know what started it."

**Protagonist:** "That's why I have to go."

**Mother:** "Then listen when you get there. Don't go looking only for what you expect."

### Choice B — "I need to know what happened to him."

**Protagonist:** "I need to know what happened to him."

**Mother:** "So do I."

*[A pause.]*

**Mother:** "But don't promise to bring him home. Not before you know what you're promising."

### Choice C — "I'm scared it won't work."

**Protagonist:** "I'm scared it won't work."

**Mother:** "I'm scared it will."

**Protagonist:** "That doesn't help."

**Mother:** "No. But I didn't want you to think you were the only one."

### Shared continuation

**Mother:** "How do you get back?"

**Protagonist:** "I've set a return signal at the gate. It keeps running while I'm away."

**Mother:** "And if the watch breaks?"

**Protagonist:** "I don't have an answer for that yet."

**Mother:** "Then be careful with it. And with yourself."

**Protagonist:** "I'll come back as soon as I've checked the other side."

**Mother:** "Good. Start with that."

**Effects:** Record the chosen response for later callbacks; set `MOTHER_DEPARTURE_TALK_DONE`. No trust loss for any of these honest responses.

## C1_05 — Workbench calibration

**Condition:** Departure conversation complete.
**Interaction:** Secure the already prepared contact in the existing watch, close the housing, and run its final test. This is the last repair in five years of work, not instant invention.

**Protagonist, on examining the failed contact:** "The contact slipped again."

**Mother:** "The small piece is in the dish. I moved it before it rolled onto the floor."

*[Player completes the authored placement.]*

**Protagonist:** "There. Stay this time."

**Watch display:** `RETURN SIGNAL — STABLE`

**Protagonist:** "It's holding."

**Mother:** "For how long?"

**Protagonist:** "Longer than yesterday."

**Mother:** "Test it again."

*[Second test; still stable.]*

**Protagonist:** "Still holding."

**Effects:** Set `WATCH_CALIBRATED`; unlock the gate anchor. The component is consumed exactly once. Missing placement produces a short status message, not a permanent quest failure.

## C1_06 — Optional time-pause test

**Availability:** Optional after calibration; only implement if the existing time-reactive-object system is working.
**Object:** A harmless moving test pendulum on the bench. It is not a dangerous machine or an essential timed puzzle.

**Protagonist:** "One more thing."

*[Player activates the authored pause effect. The test pendulum stops; other interactions remain normal.]*

**Mother:** "It stopped."

**Protagonist:** "Only that part. Only for a few seconds."

*[It resumes safely.]*

**Mother:** "I preferred it when you repaired clocks."

**Protagonist:** "Technically—"

**Mother:** "Don't."

**Rule:** Keep prototype duration/cooldown in data. Omitting this optional test does not block departure. It must not pause dialogue timers or use the menu-pause state.

## C1_07 — The memorial beside the gate

**Trigger:** Optional inspection of the small historical display before departure. The gate anchor is nearby.
**Original state:** Two empty archival mounts under weathered glass. Plaque contains the following text; no storm-night register or departure page is present.

**Plaque:** "The storm before the war. The clinic courtyard and harbor waiting shelter were unusable that night. Families scattered through the town. No complete list was made."

**Protagonist:** "Not even their names."

**Effect:** Set `ORIGINAL_MEMORIAL_READ`. Store this observed wording in the journal; do not silently rewrite the traveler's journal after history changes.

## C1_08 — Departure

**Condition:** `WATCH_CALIBRATED`; gate anchor valid.

**Mother:** "Wait."

*[She offers a repaired strap or small pouch. Use an existing suitable object.]*

**Mother:** "That strap was coming loose."

**Protagonist:** "I was going to fix it."

**Mother:** "I know."

**Watch display:**

- `VERDANT — BEFORE THE WAR`
- `RETURN SIGNAL — CONNECTED`
- `CONFIRM TRANSITION`

### Player choice A — "I'll come back."

**Mother:** "Then I'll leave the lamp on."

### Player choice B — "Thank you. For staying with me."

**Mother:** "Come back and tell me properly."

**Effect:** The player confirms travel. Fade without forced head movement. Autosave at a stable boundary, not halfway through destination loading.

---

# CHAPTER 2 — THE DOOR HE LEFT OPEN

## C2_00 — Verdant before the war

**Condition:** First successful arrival.
**Staging:** Same gate and recognizable street geometry. Intact roofs, inhabited balconies, voices, gulls, cloth awnings, and moving boats. Allow quiet exploration before dialogue.

**Protagonist, softly:** "The roofs…"

*[Neri notices the stranger, without colliding with or moving the player's camera.]*

**Neri:** "Are you lost?"

### Choice A — "I think so."

**Neri:** "Harbor's down there. Market's behind you. Try not to fall off either."

### Choice B — "I thought this street was gone."

**Neri:** "Gone where?"

**Protagonist:** "Never mind."

**Neri:** "You should sit down."

### Shared continuation

**Protagonist:** "Is there somewhere I can get some water?"

**Neri:** "The clinic. Blue shutters. Door's already open."

**Protagonist:** "Thank you."

**Neri:** "Tell him I'm not running on it."

**Protagonist:** "Running on what?"

*[Neri indicates a wrapped ankle and walks away deliberately slowly.]*

**Effect:** Set `PAST_ARRIVAL_MET_NERI`; reveal clinic objective.

## C2_01 — First meeting with the healer

**Display name:** `Healer`, never `Father` or the private writer name.
**Staging:** He is sorting supplies and attending to the room; no dramatic recognition, family theme, or revealing camera close-up.

**Healer:** "Sit down before you fall down."

**Protagonist:** "I'm not hurt."

**Healer:** "Then it's only a chair. You can still use it."

*[He indicates the water.]*

**Healer:** "Cups are beside the jug."

**Protagonist:** "You let anyone walk in?"

**Healer:** "That's why the door's open."

*[Player may take water through an ordinary interaction.]*

**Healer:** "Feeling better?"

**Protagonist:** "I think so."

**Healer:** "Good. Could you spare me a few minutes?"

**Protagonist:** "What do you need?"

**Healer:** "Sela has a parcel of clean linen for us. Her shop is just across the square."

### Choice A — "I'll bring it."

**Healer:** "Thank you. Tell her it's for the clinic."

### Choice B — "I need a moment first."

**Healer:** "Take one. The water isn't going anywhere."

**Rule:** Declining temporarily is not betrayal. Reoffer the task later without repeating the whole introduction.
**Effect on acceptance:** Start `LINEN_DELIVERY`.

## C2_02 — Sela's shop

**Condition:** Linen task accepted.

**Sela:** "Looking, buying, or bringing bad news?"

**Protagonist:** "Collecting linen for the clinic."

**Sela:** "That's almost a purchase."

*[She places a marked bundle on the counter.]*

**Sela:** "Take the wrapped one. The loose cloth is for the boats."

**Protagonist:** "Do I owe you anything?"

**Sela:** "He'll settle it. He always does, eventually."

*[A gust catches a loose piece of canvas.]*

**Protagonist:** "You expecting a storm?"

**Sela:** "Tonight. Bad enough that everyone suddenly remembers their roof leaks."

**Effect:** Give `CLINIC_LINEN` once. Do not let conversation replay duplicate it. The linen bundle is not the waterproof canvas used in the later choice.

## C2_03 — A small promise kept

**Condition:** Player actually delivers `CLINIC_LINEN` to the clinic's designated tray.

**Healer:** "You came back."

**Protagonist:** "I said I would."

**Healer:** "You'd be surprised how often that isn't enough. Thank you."

*[He unpacks the linen.]*

**Protagonist:** "Does Neri come here often?"

**Healer:** "Only when the ground wins an argument."

**Protagonist:** "He says he's not running."

**Healer:** "Then I admire his restraint."

**Effects:** Consume linen once; complete `LINEN_DELIVERY`; apply one trust event, e.g. Healer +10. This does not unlock the 100-trust perspective mechanic.

## C2_04 — One usable sheet of canvas

**Condition:** Linen delivery is complete. The healer indicates the collapsed awning over the clinic courtyard; Sela is available at her shop.

**Healer:** "There's one more thing. The courtyard awning came down. I need somewhere for people to wait when the rain starts. Sela was looking for a cover."

**Protagonist:** "I'll ask her."

*[At the shop, Sela sets out a single reinforced waterproof sheet.]*

**Sela:** "One good sheet. The others are split."

**Protagonist:** "The clinic needs it."

**Sela:** "So does the harbor waiting shelter. Its cover tore this morning."

**Protagonist:** "Who's waiting there?"

**Sela:** "Families leaving on the morning boat. Without a shelter they'll have to find rooms all over town. The clerk was hoping to register them together before they left."

**Protagonist:** "Can we cover both?"

**Sela:** "Not with this. Cut it in half and it won't reach either set of fixings. The next supply boat is tomorrow."

**Protagonist:** "What about the clinic?"

**Sela:** "He can keep his patients inside. There isn't room for all the people coming to ask after relatives. A covered courtyard would give him somewhere to speak with them and take their names."

**Protagonist:** "I'll tell him which place I take it to."

**Sela:** "Good. Don't leave anyone waiting for help that isn't coming."

**Optional line only when `ORIGINAL_MEMORIAL_READ`:**

**Protagonist, quietly:** "The courtyard. The waiting shelter."

### Destination choice

- **Clinic:** "The clinic courtyard. I'll get the awning back up."
- **Harbor:** "The waiting shelter. They need somewhere dry tonight."
- **Not yet:** "Let me look at both places first."

**Common Sela response after selecting a destination:** "All right. Take the repair straps too. Bring back whatever you don't use."

**Rules:** The player can inspect either destination before committing. Selecting a destination records a plan, not history. Commit only when the canvas is physically installed. Before installation, changing the planned destination is allowed. After installation, disable competing installation and preserve the committed result.

**Inventory:** One quest sheet `WATERPROOF_CANVAS`, plus a represented set of supplied fasteners. Do not allow infinite copies or a third outcome through decorative cloth. Do not create an arbitrary ticking real-time failure timer for this narrative choice.

## C2_05A — Clinic installation

**Condition:** Canvas owned; no cover outcome committed; clinic installation completed.

**Healer:** "Hold that corner. Yes—there."

*[Complete a safe authored placement from an accessible platform; no mandatory climbing.]*

**Protagonist:** "Will it keep the rain out?"

**Healer:** "It should. We'll put a table beneath it and bring the families through here."

*[He puts an unused ledger on the sheltered table.]*

**Protagonist:** "What will you write down?"

**Healer:** "Names. Who people are looking for. Where to send word when we find someone."

**Protagonist:** "I thought I was just fixing a roof."

**Healer:** "Now they have somewhere to come. It makes a difference."

**Effects, atomically:** Consume canvas; set `STORM_COVER = CLINIC`; mark quest complete; apply follow-through trust event once. The usable courtyard lets the clinic assemble a storm-night family-contact register. That record later becomes the displayed archive page. It does not guarantee that every patient survives the war.

## C2_05B — Harbor installation

**Condition:** Canvas owned; no cover outcome committed; harbor installation completed.
**Staging:** Sela is present or arrives by an existing plausible route, not by teleporting visibly. Neri is nearby.

**Sela:** "Pull it toward you. That's it. Tie off that side."

*[Complete the placement from the ground or an accessible platform.]*

**Neri:** "Can we sleep here now?"

**Sela:** "You can wait here. Ask your mother about sleeping."

**Protagonist:** "Whose book is that?"

**Sela:** "The departure clerk left it. Now everyone can gather here, he can take their names before the boats leave."

**Protagonist:** "For the fares?"

**Sela:** "For anyone who comes looking after the boat has gone."

**Effects, atomically:** Consume canvas; set `STORM_COVER = HARBOR`; mark quest complete; apply follow-through trust event once. The usable shelter lets the clerk assemble a storm-night passenger list that would otherwise have remained incomplete. That record later becomes the displayed archive page. It does not guarantee that every departing family is safe forever.

## C2_06 — Report back

**Condition:** A cover outcome is committed; first return to the healer after completion.

### When clinic was covered

**Protagonist:** "The harbor still needs a cover."

**Healer:** "Then we'll see what we can move inside before the rain. Thank you for telling me."

### When harbor was covered

**Protagonist:** "I used the sheet at the harbor. I'm sorry."

**Healer:** "Was there only one?"

**Protagonist:** "One that would hold."

**Healer:** "Then I'll ask people to wait with their neighbors. You helped where you could."

### Optional question — "What if something worse is coming?"

**Protagonist:** "What if something worse is coming?"

**Healer:** "Worse than the storm?"

**Protagonist:** "A war."

*[He takes the statement seriously rather than laughing or instantly believing every detail.]*

**Healer:** "Have you heard something?"

**Protagonist:** "I know what happens afterward. I don't know where it starts."

**Healer:** "Then find something we can act on. A place. A date. Someone we can speak to."

**Protagonist:** "And you'll listen?"

**Healer:** "I'm listening now."

### Shared departure

**Protagonist:** "I need to go home."

**Healer:** "Then go. Someone will be waiting."

**Protagonist:** "Will you be here when I come back?"

**Healer:** "Most days. You know where the door is."

**Effects:** Set `HEALER_REPORT_DONE`. Do not reveal his identity. Unlock the guided return objective.

## C2_07 — Return signal

**Location:** The same courtyard gate anchor.

**Watch display:**

- `RETURN SIGNAL — AVAILABLE`
- `HOME — PRESENT`
- `CONFIRM TRANSITION`

**Protagonist:** "Let's see what stayed."

**Rule:** Load the committed consequence variant. Do not advance quest state before destination restoration succeeds. Returning later to the past uses the committed history, not a fresh canvas quest.

## C2_08A — Present consequence: the clinic register

**Condition:** `STORM_COVER = CLINIC`.
**Visual:** One formerly empty archive mount now contains a preserved register page and a new explanatory caption; the harbor-book mount remains empty. The damaged city and house remain damaged.

**New caption:** "A covered clinic courtyard became a meeting point during the storm. The register assembled there later helped families find their relatives. These pages preserve some of their names."

### When the original memorial was inspected

**Protagonist:** "This frame was empty."

### Otherwise

**Protagonist:** "They wrote the names down. In the courtyard."

**Mother, approaching from the house:** "What are you looking at?"

**Protagonist:** "I put up the awning. Before the rain."

**Mother:** "The register's been here for years."

**Protagonist:** "Not for me."

*[She sees his expression and stops trying to explain it away.]*

**Mother:** "All right. Tell me."

**Effects:** Record the observed change. Preserve any original journal entry as a prior-timeline observation.

## C2_08B — Present consequence: the harbor book

**Condition:** `STORM_COVER = HARBOR`.
**Visual:** The harbor archive mount contains a preserved departure page; the clinic mount remains empty. The damaged city and house remain damaged.

**New caption:** "The repaired waiting shelter brought departing families together during the storm. The passenger list assembled there later helped relatives trace where they had gone."

### When the original memorial was inspected

**Protagonist:** "There weren't any names here before."

### Otherwise

**Protagonist:** "The departure list. They managed to record everyone waiting there."

**Mother, approaching from the house:** "Whose name are you looking for?"

**Protagonist:** "No one's. I just needed to know they made the list."

**Mother:** "It's been here for years."

**Protagonist:** "I know. That's the strange part."

**Mother:** "Come inside. Start at the beginning."

**Effects:** Record the observed change. Preserve prior-timeline observations.

## C2_09 — The lamp is still on

**Location:** Surviving family room, after the return consequence.
**Staging:** The lamp is lit. The protagonist sets the watch down or lowers his wrist voluntarily. Do not trigger a forced camera animation.

**Mother:** "You're shaking."

**Protagonist:** "I don't think I noticed until now."

*[She brings a cup and sits nearby.]*

**Mother:** "Did it work?"

**Protagonist:** "I was there. Before the roofs fell. Before any of this."

**Mother:** "What was it like?"

**Protagonist:** "Loud."

*[A small, startled laugh from her.]*

**Mother:** "Yes."

**Protagonist:** "Someone was complaining about the rain. I wanted to tell them how lucky they were."

**Mother:** "Did you?"

**Protagonist:** "No. I helped with a roof."

### Choice A — "It wasn't enough."

**Mother:** "For what?"

**Protagonist:** "To stop any of this."

**Mother:** "You went once. Sit down before you decide what that means."

### Choice B — "I changed something."

**Mother:** "I believe you."

**Protagonist:** "Even though you remember it differently?"

**Mother:** "I can see you're trying to tell me the truth."

### Choice C — "I don't know what to do next."

**Mother:** "Eat. Sleep. Then tell me everything you remember."

### Shared ending

**Protagonist:** "I'm going back."

**Mother:** "Tomorrow."

**Protagonist:** "Tomorrow."

*[Let the player look around. The ruined room remains, but an ordinary domestic moment has returned to it.]*

**Journal, if original memorial inspected:** "The town remembers a different version of the storm. I remember the empty display and what I did in the past. Mother remembers the new record being here for years. I can change something. I still don't know what started the war."

**Otherwise:** "A record of the storm-night shelter is on display in the present. Mother says it has been here for years. I remember helping make it possible. I still don't know what started the war."

**Completion:** Set `CHAPTER_2_COMPLETE`; save at a stable state. Fade only after the player advances the final line. Show end-of-slice screen or return to the approved hub, not an unimplemented next chapter.

---

## 3. Optional repeat and locked-action lines

Keep these sparse and use cooldowns so the player is not nagged.

### Mother, after her main conversation but before departure

**Mother:** "The lamp will be here when you get back."

### Healer, while the accepted linen task is pending

**Healer:** "Sela's parcel should be wrapped and ready."

### Sela, after canvas has been collected

**Sela:** "You have the only sound sheet. Check the fixings before you settle on a place."

### Healer, after his chapter conversation is exhausted

**Healer:** "I should get back to work. You're welcome to the water."

### Perspective before eligibility

**Watch display only:** `PERSPECTIVE UNAVAILABLE — RELATIONSHIP NOT YET READY`

Do not make a character announce their trust percentage. Do not award 100 trust just to force a tutorial into the first encounter.

### Future perspective consent dialogue

**Availability:** Store for later use. Enable only when trust is genuinely 100 and the specific authored view exists.

**Protagonist:** "The watch might let me see what you're seeing. Only for a few seconds."

**NPC:** "You'd have to ask me first."

**Protagonist:** "That's what I'm doing. You can stop it."

**NPC:** "All right. Just this once."

Consent is separate from trust. Show a stationary perspective for no more than thirty seconds, with an immediate exit action. No forced NPC head motion, unrestricted possession, or unannounced access to thoughts. These lines are not proof that the feature is implemented.

---

## 4. Quest, branch, and save contract

### Required flags and states

- `PHOTO_READ`: boolean.
- `LETTER_READ`: boolean.
- `MOTHER_DEPARTURE_TALK_DONE`: boolean.
- `MOTHER_OPENING_RESPONSE`: STOP_WAR / FIND_FATHER / AFRAID.
- `WATCH_CALIBRATED`: boolean.
- `ORIGINAL_MEMORIAL_READ`: boolean.
- `PAST_ARRIVAL_MET_NERI`: boolean.
- `LINEN_DELIVERY`: NOT_ACCEPTED / ACCEPTED / COLLECTED / DELIVERED.
- `CANVAS_OWNED`: boolean.
- `CANVAS_PLAN`: NONE / CLINIC / HARBOR; reversible until installation.
- `STORM_COVER`: NONE / CLINIC / HARBOR; committed once per save history.
- `HEALER_REPORT_DONE`: boolean.
- `CONSEQUENCE_OBSERVED`: boolean.
- `CHAPTER_2_COMPLETE`: boolean.
- Relationship values and a set of already-applied relationship-event IDs.
- Current era, safe anchor, return-signal metadata, and prior-timeline journal observations.

### Transition contract

1. Collecting an item and recording the collection are one atomic state change.
2. A conversation line alone cannot complete a physical delivery or installation.
3. Delivering linen consumes the quest item and applies its trust reward once.
4. Installing the canvas consumes it and commits exactly one destination in the same transaction.
5. No installation is permitted after `STORM_COVER != NONE`.
6. Return travel in the guided opening is unavailable while a required delivery is in an unsafe partial state. Explain the pending task through the objective, not a silent failed button.
7. The two consequence scenes are mutually exclusive. The default original display is used only before a committed past intervention.
8. Consequence restoration reads saved authoritative state. It must not reroll, replay rewards, or assume the most recently displayed dialogue choice was committed.
9. Pause or interruption must not select a default response. Resume at a safe point or repeat a short noncommitting line.
10. Only one voiced/subtitled line owns the dialogue channel at a time. Nearby ambient chatter must yield to important dialogue.
11. Brief parenthetical staging directions are never spoken. Optional variants appear only under their stated conditions.
12. All three final emotional responses lead to the same chapter completion. They express personality, not hidden good/bad ending points.

### Production staging

- Use gestures already available; do not make the entire chapter depend on bespoke cinematics.
- A text-only prototype must still be playable.
- Do not use modern copyrighted music or unauthorized voice clones.
- Keep the family house structurally recognizable across eras.
- The archive props are a bounded visual change suitable for this slice. Do not rebuild the whole island because of the canvas choice.
- The canvas enables a usable communal space and therefore a new record of people gathered there. Do not rewrite the stakes as choosing which small portable book to save: the player could simply carry both books.
- People at the unchosen site still seek shelter elsewhere. Do not imply that choosing one location automatically kills people at the other.
- Neither the future dialogue nor the archive captions should claim that the first intervention prevented the war.
- Do not narrate the protagonist's emotions constantly. Silence is part of the script.
- Do not name the healer's family, place his signature on the displayed register, or show a father portrait during these chapters.

## 5. Acceptance checks

Test each canvas outcome with and without original memorial inspection: four complete consequence routes. Also test every Mother response, the optional time-pause test being skipped, and temporary refusal of the linen task.

Verify:

- The protagonist never speaks an unselected response.
- Opening objects can be inspected in either order.
- Repeated inspection does not duplicate inventory or trust.
- The player cannot own two canvases or install one at both sites.
- Changing a planned destination before installation works.
- The displayed record matches the actual installed cover, including after save/load.
- No skipped scene leaves a permanent blocker.
- The mother's memories match the changed timeline; the player's journal preserves observed history.
- The world remains war-damaged after the small intervention.
- The healer's identity is not exposed in any player-facing channel.
- The first encounter does not automatically unlock 100-trust perspective.
- Audio absence does not disable the dialogue flow.
- VR camera tracking is never overridden by cinematic gestures.

Report actual editor, gameplay, and packaged-build checks separately. Written content validation is not a gameplay test.

## 6. Implementation order

1. Add and validate dialogue content and choices in the existing content format.
2. Connect Chapter 1 objects, Mother, calibration, and departure.
3. Connect Chapter 2 arrival, healer, Sela, linen delivery, and the two canvas sites.
4. Connect the appropriate present-day record and ending conversation.
5. Verify state recovery, save/load, subtitles, and branch exclusivity.
6. Add restrained animation/audio polish after the full text-first route works.

**Success condition:** The player leaves a damaged home, meets people in a living town, keeps a small promise, makes a real choice, returns to a changed record of history, and comes home to Mother—without learning the healer's secret identity yet.
