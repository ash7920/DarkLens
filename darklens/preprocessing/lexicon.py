"""
Rule lexicon: cheap, transparent patterns per category.

Used (1) as the "Rules" baseline in the evaluation, (2) as a high-recall
candidate pre-filter before the LLM, and (3) in the offline screenshot mode.
Patterns cover English plus common DE/FR/ES/IT/NL phrasing.
"""
from __future__ import annotations

import re

from ..taxonomy import NOT_DARK

_T = r"\d{1,2}\s*[:hH]\s*\d{2}(\s*[:mM]\s*\d{2})?"  # 00:14:59 / 2h 30m

RULES: dict[str, list[str]] = {
    "urgency": [
        rf"(ends?|ending|expires?|left|endet|termine|termina|eindigt|scade)\b.{{0,25}}{_T}",
        rf"{_T}.{{0,15}}(left|remaining|restant|restantes|übrig|rimast)",
        r"limited[- ]time|for a limited time|today only|only today|ends (today|tonight|soon|in)",
        r"flash sale|last chance|hurry|don'?t miss|while it lasts|act now|deal of the day",
        r"nur (noch )?heute|nur für kurze zeit|letzte chance|endet (bald|heute|in)",
        r"temps limité|dernière chance|aujourd'hui seulement|vente flash",
        r"tiempo limitado|última oportunidad|solo hoy|oferta flash|termina en",
        r"tempo limitato|ultima occasione|solo oggi|offerta lampo",
        r"beperkte tijd|alleen vandaag|laatste kans",
        r"reserved for \d+|held for \d+|reserviert für",
    ],
    "scarcity": [
        r"only \d+ (left|remaining|available|in stock)|(just|only) \d+ (items? )?left",
        r"\d+ (left|remaining) in stock|low stock|almost (gone|sold out)|selling fast|limited stock",
        r"high demand|in high demand|popular item|\d+ (people )?(have|has) (this|it) in (their )?(cart|basket|bag)",
        r"nur noch \d+|wenige verfügbar|fast ausverkauft|hohe nachfrage",
        r"plus que \d+|il ne reste (plus )?que \d+|stock limité|bientôt épuisé",
        r"(sólo|solo) quedan \d+|últimas unidades|pocas unidades",
        r"(solo|ultimi) \d+ (rimast|disponibil)|quasi esaurito",
        r"nog maar \d+|bijna uitverkocht",
    ],
    "social_proof": [
        r"\b\d+ (people|persons|customers|shoppers|others|users) (are )?(viewing|looking|watching|bought|purchased)",
        r"\b(just|recently) (bought|purchased|ordered)\b",
        r"\bfrom [A-Z][a-z]+.{0,40}(bought|purchased|ordered)",
        r"(bought|purchased|ordered).{0,20}\b\d+ (seconds?|minutes?|hours?) ago",
        r"viewed (this )?\d+ times|\d+ (views|sold) (in the last|today|this week)",
        r"personen (sehen|schauen|haben).{0,20}(an|gekauft)|gerade gekauft",
        r"personnes (regardent|ont acheté)|vient d'acheter",
        r"personas (están viendo|han comprado)|acaba de comprar",
        r"persone (stanno guardando|hanno acquistato)|ha appena acquistato",
    ],
    "confirmshaming": [
        r"no,? (thanks|thank you)?,? ?i (don'?t|do not|prefer|would rather|'?d rather|hate|like paying|want to)",
        r"i('?d| would) rather (pay|miss|not save|stay)",
        r"no,? i (don'?t|do not) (want|like|care|need)",
        r"i('?ll| will) pass on",
        r"i (don'?t|do not) (like|want) (free|saving|discounts|deals|money)",
        r"(prefer|rather) (paying|to pay) full price",
        r"nein,? ich (will|möchte) (keine|nicht).{0,20}(sparen|rabatt)",
        r"non,? je (ne veux pas|préfère payer)",
        r"no,? (prefiero pagar|no quiero ahorrar)",
    ],
    "preselection": [
        r"\[x\]|\(pre-?(ticked|selected|checked)\)|pre-?ticked|pre-?selected",
        r"(protection|insurance|warranty|donation|donate|gift wrap|priority|express).{0,40}(\+|€|£|\$)\s?\d",
        r"(service|handling|booking|processing|convenience) fee",
        r"added to (your )?(cart|basket|bag)",
        r"(servicegebühr|bearbeitungsgebühr|frais de service|frais de dossier|cargo por servicio|gastos de gestión|costi di servizio)",
    ],
    "obstruction": [
        r"(to|in order to) cancel.{0,80}(call|phone|contact|write|visit|letter|chat)",
        r"cancel(lation)? (only|is only possible) (by|via) (phone|post|mail|letter)",
        r"you will lose (all )?(your )?(benefits|rewards|points|savings)",
        r"(keep|stay with) (my|your) (benefits|membership|plan|subscription)",
        r"kündigung (nur )?(per|telefonisch|schriftlich)|(résiliation|cancelación|disdetta).{0,40}(téléphone|teléfono|telefono|courrier)",
    ],
    "interface_interference": [
        r"uncheck (this|the) box if you (do not|don'?t) (wish|want)",
        r"(do not|don'?t) (not )?(un)?check",
    ],
    "forced_action": [
        r"(create|register|sign up for) an account to (continue|see|view|checkout|proceed)",
        r"guest checkout (is )?not available|(login|sign in|log in) required to",
        r"enter your email to (continue|see|unlock|view)",
        r"konto erstellen,? um|créez un compte pour|crea una cuenta para",
    ],
}

COMPILED = {k: [re.compile(p, re.I) for p in v] for k, v in RULES.items()}


def rule_matches(text: str) -> list[tuple[str, str]]:
    """All (category, matched_span) pairs for a text."""
    hits = []
    for cat, pats in COMPILED.items():
        for p in pats:
            m = p.search(text or "")
            if m:
                hits.append((cat, m.group(0)))
                break
    return hits


def rule_label(text: str) -> str:
    """Single best label — first matching category in a fixed precedence order."""
    hits = rule_matches(text)
    if not hits:
        return NOT_DARK
    order = ["confirmshaming", "obstruction", "forced_action", "preselection", "social_proof",
             "urgency", "scarcity", "interface_interference"]
    cats = {c for c, _ in hits}
    for c in order:
        if c in cats:
            return c
    return hits[0][0]
