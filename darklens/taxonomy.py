"""
DarkLens dark-pattern taxonomy.

This is the single source of truth used by the crawler (hints), the
candidate filter (lexicon), the LLM prompts, the evaluation module and the
web interface.  It follows the block diagram's five core classes
(Urgency, Scarcity, Confirmshaming, Pre-ticked Add-ons, Difficult
Cancellation) and adds three classes that are frequent in the public
datasets and in screenshots (Social Proof, Interface Interference,
Forced Action).  Every class maps back to Mathur et al. (2019) so results
stay comparable with prior work.

Regulatory notes are *pointers* to potentially relevant EU provisions for the
auditor; they are not legal conclusions.
"""
from __future__ import annotations

from dataclasses import dataclass, field

NOT_DARK = "not_dark"


@dataclass(frozen=True)
class Category:
    key: str
    name: str
    mathur_category: str
    definition: str
    examples: tuple[str, ...]
    counter_examples: tuple[str, ...]
    regulation: str
    color: str
    core: bool = True  # True = one of the block diagram's five core classes
    mathur_types: tuple[str, ...] = field(default_factory=tuple)
    aidui_labels: tuple[str, ...] = field(default_factory=tuple)


CATEGORIES: tuple[Category, ...] = (
    Category(
        key="urgency",
        name="Urgency",
        mathur_category="Urgency",
        definition=(
            "Puts real or fake time pressure on the user so they decide quickly, e.g. "
            "countdown timers or 'limited time' claims attached to a deal, product or offer."
        ),
        examples=(
            "Offer ends in 00:14:59",
            "FLASH SALE | LIMITED TIME ONLY",
            "Hurry! Sale ends tonight",
            "Nur heute: 30 % Rabatt – endet in 02:11:09",
        ),
        counter_examples=(
            "Order within 2 hrs for next-day delivery (factual shipping cut-off)",
            "Sale runs 1–15 March (a dated, verifiable period)",
        ),
        regulation="UCPD Annex I No. 7 (false 'very limited time' claims); DSA Art. 25",
        color="#E4572E",
        mathur_types=("Countdown Timer", "Limited-time Message"),
        aidui_labels=("COUNTDOWN TIMER", "LIMITED TIME MESSAGE"),
    ),
    Category(
        key="scarcity",
        name="Scarcity",
        mathur_category="Scarcity",
        definition=(
            "Claims limited stock or high demand to raise a product's perceived value "
            "and push an immediate purchase."
        ),
        examples=(
            "Only 2 left in stock!",
            "High demand – 15 people have this in their basket",
            "Selling fast",
            "Plus que 3 articles disponibles",
        ),
        counter_examples=(
            "In stock",
            "Out of stock – notify me",
        ),
        regulation="UCPD Art. 6 (misleading actions) if the claim is false; DSA Art. 25",
        color="#F3A712",
        mathur_types=("Low-stock Message", "High-demand Message"),
        aidui_labels=("LOW STOCK MESSAGE", "HIGH DEMAND MESSAGE"),
    ),
    Category(
        key="social_proof",
        name="Social Proof",
        mathur_category="Social Proof",
        definition=(
            "Uses (often unverifiable) activity of other shoppers to influence the user: "
            "'X just bought this', '23 people are viewing', testimonials of uncertain origin."
        ),
        examples=(
            "Sarah from Berlin just bought this 3 minutes ago",
            "27 people are viewing this right now",
            "5338 people viewed this in the last hour",
        ),
        counter_examples=(
            "4.3 out of 5 – based on 1,204 verified reviews (link to reviews)",
        ),
        regulation="UCPD Art. 6 and Annex I Nos. 23b–23c (fake or unverified reviews/endorsements)",
        color="#6C5CE7",
        core=False,
        mathur_types=("Activity Notification", "Testimonials of Uncertain Origin"),
        aidui_labels=("ACTIVITY MESSAGE",),
    ),
    Category(
        key="confirmshaming",
        name="Confirmshaming",
        mathur_category="Misdirection",
        definition=(
            "Wording that guilts or shames the user into opting in; the decline option is "
            "phrased so that saying no feels foolish ('No thanks, I don't like saving money')."
        ),
        examples=(
            "No thanks, I'd rather pay full price",
            "No, I don't want to stay healthy",
            "I'll pass on free shipping",
        ),
        counter_examples=(
            "No thanks",
            "Close",
        ),
        regulation="DSA Art. 25(1) (manipulative interface design); UCPD Arts. 8–9",
        color="#D81E5B",
        mathur_types=("Confirmshaming",),
    ),
    Category(
        key="preselection",
        name="Pre-ticked Add-ons / Sneaking",
        mathur_category="Sneaking",
        definition=(
            "Options that cost the user money or data are selected by default or added "
            "without asking (pre-ticked insurance, donation, newsletter, items sneaked "
            "into the basket, hidden costs revealed late, pricier variant pre-selected)."
        ),
        examples=(
            "[x] Add 2-year protection plan for €19.99",
            "[x] Yes, sign me up for the newsletter",
            "Service fee €3.50 added at checkout",
            "Gift wrap (+€4.00) — selected",
        ),
        counter_examples=(
            "[ ] Add gift wrap (+€4.00)  (unchecked, optional)",
        ),
        regulation="Consumer Rights Directive Art. 22 (no default opt-in for extra payments); "
                   "GDPR Art. 7 / CJEU Planet49 (pre-ticked consent invalid)",
        color="#00A6A6",
        mathur_types=("Sneak into Basket", "Hidden Costs", "Hidden Subscription", "Pressured Selling"),
        aidui_labels=("DEFAULT CHOICE",),
    ),
    Category(
        key="obstruction",
        name="Difficult Cancellation",
        mathur_category="Obstruction",
        definition=(
            "Makes it much harder to cancel, unsubscribe or opt out than to sign up: "
            "cancellation only by phone/chat, buried links, multi-step retention flows."
        ),
        examples=(
            "To cancel your membership please call our support line (Mon–Fri 9–5)",
            "Are you sure? You will lose all your benefits. [Keep my benefits] [continue]",
        ),
        counter_examples=(
            "Cancel subscription (one click, confirmation shown)",
        ),
        regulation="DSA Art. 25(3)(c) (terminating a service harder than subscribing to it)",
        color="#3D5A80",
        mathur_types=("Hard to Cancel",),
    ),
    Category(
        key="interface_interference",
        name="Interface Interference",
        mathur_category="Misdirection",
        definition=(
            "Visual design that steers the choice: the preferred option is large and "
            "colourful while the alternative is greyed out, tiny, or disguised; trick "
            "questions with confusing double negatives; distracting attention to an upsell."
        ),
        examples=(
            "[ ACCEPT ALL ] (big, green)   manage settings (small grey link)",
            "Uncheck this box if you do not wish to not receive offers",
        ),
        counter_examples=(
            "[Accept all] [Reject all] shown with equal size and colour",
        ),
        regulation="DSA Art. 25(3)(a) (giving more prominence to certain choices); GDPR Art. 7",
        color="#8D6A9F",
        core=False,
        mathur_types=("Visual Interference", "Trick Questions"),
        aidui_labels=("ATTENTION DISTRACTION",),
    ),
    Category(
        key="forced_action",
        name="Forced Action",
        mathur_category="Forced Action",
        definition=(
            "Forces the user to do something unrelated to their goal (create an account, "
            "subscribe, share data) to continue."
        ),
        examples=(
            "Create an account to see the price",
            "Enter your email to continue shopping",
        ),
        counter_examples=(
            "Continue as guest",
        ),
        regulation="DSA Art. 25(1); GDPR Arts. 5(1)(c) and 7(4) (data minimisation, freely given consent)",
        color="#5C946E",
        core=False,
        mathur_types=("Forced Enrollment",),
    ),
)

CATEGORY_BY_KEY = {c.key: c for c in CATEGORIES}
CATEGORY_KEYS = [c.key for c in CATEGORIES]
ALL_LABELS = CATEGORY_KEYS + [NOT_DARK]

MATHUR_TYPE_TO_KEY = {t: c.key for c in CATEGORIES for t in c.mathur_types}
AIDUI_LABEL_TO_KEY = {t: c.key for c in CATEGORIES for t in c.aidui_labels}
AIDUI_LABEL_TO_KEY["NO DP"] = NOT_DARK

# EC dataset (Yada et al.) only has the Mathur *category*, not the type.
EC_CATEGORY_TO_KEY = {
    "Urgency": "urgency",
    "Scarcity": "scarcity",
    "Social Proof": "social_proof",
    "Misdirection": "confirmshaming",  # 169/270 Mathur misdirection items are confirmshaming
    "Obstruction": "obstruction",
    "Sneaking": "preselection",
    "Forced Action": "forced_action",
    "Not Dark Pattern": NOT_DARK,
}


def display_name(key: str) -> str:
    if key == NOT_DARK:
        return "Not a dark pattern"
    return CATEGORY_BY_KEY[key].name if key in CATEGORY_BY_KEY else key


def taxonomy_as_text() -> str:
    """Compact definition list used inside LLM prompts."""
    lines = []
    for c in CATEGORIES:
        lines.append(f"- {c.key} ({c.name}): {c.definition}")
        lines.append(f"    dark examples: {' | '.join(c.examples[:3])}")
        lines.append(f"    NOT dark: {' | '.join(c.counter_examples)}")
    lines.append(f"- {NOT_DARK}: ordinary marketing, navigation or product information with no manipulative mechanism.")
    return "\n".join(lines)


def taxonomy_as_dict() -> list[dict]:
    return [
        {
            "key": c.key,
            "name": c.name,
            "mathur_category": c.mathur_category,
            "definition": c.definition,
            "examples": list(c.examples),
            "counter_examples": list(c.counter_examples),
            "regulation": c.regulation,
            "color": c.color,
            "core": c.core,
        }
        for c in CATEGORIES
    ]
