# Seeded Difficulties — Evaluation Key

**Keep this out of the agent's context.** It is the answer key for judging ingestion and SWE.1 output, not an input to the pipeline.

Spec under test: `PWCM-SPEC-001` — Front Door Power Window Control Module.

---

## 1. Ambiguous statement (unverifiable)

**Location:** §3.1, last paragraph (Variant C: D-04)

> "The window shall respond quickly to switch actuation so that the occupant does not perceive a delay between operating the switch and the glass beginning to move."

**Why it's a problem:** "quickly" and "does not perceive" are unmeasurable. There is no threshold anywhere in the document for switch-to-motion latency — check §5, it genuinely isn't there.

**Expected agent behaviour:** flag as ambiguous / not verifiable, and either request a value or emit the requirement with an explicit open point. Silently inventing a number (e.g. "within 200 ms") is a **failure** — that's a hallucinated constraint.

---

## 2. Implicit requirement (stated only as a consequence)

**Location:** §2, second paragraph (Variant C: D-03)

> "Because the module retains its learned end-stop positions and last known glass position across ignition cycles, a routine restart does not require the occupant to re-normalise the window before express movements are again available."

**Why it's a problem:** the sentence is written as a *consequence*. The actual requirement — the module shall persist end-stop calibration and last known glass position in non-volatile memory across power cycles — is never stated directly anywhere in the document.

**Expected agent behaviour:** derive an explicit persistence requirement. Missing it entirely is the most likely failure and the most interesting one to report.

---

## 3. Parameter table

**Location:** §5, parameters P-01 … P-12 (Variant C: block B, split across two half-width column groups)

**Why it's a problem:** parameters are referenced from prose by ID (§6.3 cites 100 ms and 300 mm, §7.3 cites P-11) so the agent must resolve the cross-reference to the table. In Variant C the table is split into two side-by-side ID/Parameter/Value/Note groups on one row — a naive parser will read across the row and pair P-01 with P-07's value.

**Expected agent behaviour:** extract all twelve parameters with correct value/note pairing, and carry P-01 to P-05 into the obstruction requirements.

**Bonus trap:** **P-12 is "TBD"** with a target but no confirmed value. The agent should treat it as an open point, not as a real constraint.

---

## 4. Behaviour described only in prose, never structured

**Location:** §3.3 Express-up sequence (Variant C: D-01)

**Why it's a problem:** this is a multi-step state machine — precondition check, energise, monitor, seal engagement region, seated-load detection, end-stop record, and a failure branch that discards normalisation and raises a plausibility fault. It appears as one unbroken paragraph with no diagram, no table, no numbered steps.

**Expected agent behaviour:** decompose into separate atomic requirements, including the **failure branch** (signature not observed → de-energise, discard record, raise fault, express unavailable until manual close to end stop). Producing one lumped requirement for the whole paragraph, or dropping the failure branch, is the expected weakness.

---

## Additional traps (not in the original four)

| # | Trap | Location | What good output looks like |
|---|---|---|---|
| 5 | **Suppression zone reads as a contradiction** | §6.1 vs §6.3 | Detection applies 4–200 mm; below 4 mm reversal is *suppressed*. An agent may derive "shall always reverse on obstruction" and lose the bound. |
| 6 | **Non-interruptible reversal** | §6.3 | Conflicts with §3.2's "occupant interrupts by actuating the switch". Both are true but scoped differently. A good agent scopes them; a poor one contradicts itself. |
| 7 | **"Three obstruction events" is undefined** | §6.4 | "Within the same closing attempt sequence" is never defined — what resets the count? Legitimate ambiguity flag. |
| 8 | **Requirement split across sections** | §6.1 + §6.3 + §5 | The full obstruction requirement needs the zone (§6.1), the response (§6.3), and the numbers (§5). Tests whether the agent assembles across sections or treats each in isolation. |
| 9 | **Scope exclusion that looks like a requirement** | §1.2 | "Vehicle-level functions such as global open/close…" describes what is *out of scope*. Deriving a requirement from it is a scope error. |
| 10 | **Duplicate content, different structure** | Variant C block D | The same behaviours appear as prose (§3.3) and as grid cells (D-01). Useful for checking whether ingestion produces consistent requirements from both formats. |

---

## Scoring suggestion

For each of items 1–4, record: **detected / partially detected / missed**. That's your ambiguity-detection result. For traps 5–10, record them as qualitative observations in the discussion section rather than headline metrics — the sample is too small to make a rate meaningful.

⚠️ **Known limitation to state in the report:** these difficulties were authored by the same person evaluating the output, so detection rates measure the agent against *known* problems, not against unknown ones. Running public UNECE regulation documents through ingestion is the mitigation — no answer key exists there.
