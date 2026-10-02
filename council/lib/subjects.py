"""Shared readers for the subject's basket, theme and asset-class fields
(THEMES-BASKETS-SPEC section 2; ANCHORLESS-SPEC section 2).

One definition, imported everywhere: how a ticker becomes a fact-id
suffix, which tickers a subject's expression names, where the theme
block lives, the two core facts every named expression member must
carry, and whether the subject's asset class is ANCHORED or ANCHORLESS.
The gate, the sufficiency check and the engine all read the subject
through these helpers, so the id arithmetic is written exactly once.

The subject carries two independent readings and they are not the same
thing. `kind` is its SHAPE - one listed name, a fund, a basket of names,
a theme, a coin, bullion, a commodity contract - and it decides which
structural fields the capture may carry. `asset_class` is what the thing
economically IS, and it decides the sufficiency anchor set and the
rating basis. A Bitcoin fund has the shape of a fund and the substance
of crypto, which is exactly why the two readings are kept separate.
"""

from datetime import date


def applies_on(entry, captured_day):
    """AC46(2): a dated floor or anchor binds from its ruled day onward."""
    return (not entry.get("applies_from")
            or captured_day >= date.fromisoformat(entry["applies_from"]))


# The classes whose subjects have no earnings to anchor on, so their
# rating is EARNED from a scenario ladder instead of read off the four
# canonical tests (ANCHORLESS-SPEC section 3, owner ruling AB13.1).
ANCHORLESS_CLASSES = ("crypto", "gold", "commodity")

# Each SHAPE that fixes its own class, and the one class it may declare:
# a listed share is an equity, a coin is crypto, bullion is gold, a
# commodity contract is a commodity. The collective shapes - a fund, a
# basket, a theme - may wrap ANY class, which is how a fund holding
# coins is judged as crypto through the fund.
SHAPE_CLASS = {
    "single_stock": "equity",
    "bitcoin": "crypto",
    "gold": "gold",
    "commodity": "commodity",
}

# The core fact concepts every named expression member carries in
# tier1, one fact per member per concept, id-suffixed with the member's
# slug: <concept>__<slug(ticker)>.
PER_EXPRESSION_CORE = ("price_last", "market_cap")


def slug(ticker):
    """A ticker as a fact-id suffix: lowercased, every character
    outside [a-z0-9] replaced with an underscore."""
    return "".join(
        char if ("a" <= char <= "z" or "0" <= char <= "9") else "_"
        for char in str(ticker).lower())


def constituent_tickers(subject):
    """The declared constituents' tickers in declaration order; empty
    where the subject declares none."""
    return [item["ticker"] for item in subject.get("constituents") or ()]


def expression_tickers(subject):
    """Every ticker the subject's expression names: the constituents',
    else the vehicle's alone, else none."""
    tickers = constituent_tickers(subject)
    if tickers:
        return tickers
    vehicle = subject.get("vehicle")
    if vehicle:
        return [vehicle["ticker"]]
    return []


def theme_block(subject):
    """The subject's theme block, or None where none is declared."""
    return subject.get("theme") or None


def has_constituents(subject):
    """True where the subject declares a constituent list."""
    return bool(subject.get("constituents"))


def asset_class(subject):
    """The subject's declared asset class."""
    return subject.get("asset_class")


def is_anchorless(subject):
    """True where the subject's asset class has no earnings to anchor a
    rating on, so the rating must be EARNED from a scenario ladder
    (ANCHORLESS-SPEC section 3)."""
    return asset_class(subject) in ANCHORLESS_CLASSES


def product(subject):
    """A commodity's product or a coin, or None."""
    return subject.get("product") or None


def coin(subject, floors):
    """The crypto subject's registry key (owner ruling AC67(4))."""
    if asset_class(subject) != "crypto":
        return None
    rule = (class_registry(floors, subject) or {}).get("monetary_coin_rule") or {}
    return product(subject) or rule.get("unnamed_coin")


def coin_applies_on(subject, floors, captured_day, entry=None):
    """Architect ruling 5: named coins bind regardless of date.

    AC46(2) protects earlier unnamed records. Only appended coin anchors
    share the coin rule's binding; every other entry keeps its own date.
    """
    registry = class_registry(floors, subject) or {}
    rule = registry.get("monetary_coin_rule") or {}
    is_coin = subject.get("kind") in rule.get("coin_kinds", ())
    bound = is_coin and (named_coin(subject, floors) is not None
                         or applies_on(rule, captured_day))
    if entry is None:
        return bound
    dated = applies_on(entry, captured_day)
    if is_coin and entry in coin_appended_anchors(floors, subject):
        later = entry.get("applies_from", "") > rule.get("applies_from", "")
        return bound and (dated if later else True)
    return dated


def named_coin(subject, floors):
    """M1, AC67(4): the named registry coin on a coin-kind subject."""
    registry = (floors.get("asset_classes") or {}).get("crypto") or {}
    rule = registry.get("monetary_coin_rule") or {}
    key = product(subject)
    return key if (subject.get("kind") in rule.get("coin_kinds", ())
                   and key in (registry.get("products") or {})) else None


def coin_appended_anchors(floors, subject):
    """M7: the coin, common coin and privacy anchors, in ruled order."""
    registry = class_registry(floors, subject) or {}
    rule = registry.get("monetary_coin_rule") or {}
    row = (registry.get("products") or {}).get(coin(subject, floors)) or {}
    anchors = list(row.get("anchors") or ()) + list(rule.get("anchors") or ())
    if row.get("privacy_coin"):
        anchors += list(rule.get("privacy_coin_anchors") or ())
    return anchors


def class_anchors_on(floors, subject, captured_day):
    """M6, AC71(3): binding anchors, with source words on copies only."""
    registry = class_registry(floors, subject) or {}
    rule = registry.get("monetary_coin_rule") or {}
    bound = coin_applies_on(subject, floors, captured_day)
    sources = rule.get("class_anchor_source_words") or {}
    return [dict(entry, likely_source=sources[entry["id"]])
            if bound and entry.get("id") in sources else entry
            for entry in class_anchors(floors, subject)
            if coin_applies_on(subject, floors, captured_day, entry)]


def class_registry(floors, subject):
    """The floors entry for this subject's asset class, or None where the
    file carries none for it."""
    return (floors.get("asset_classes") or {}).get(asset_class(subject))


def class_anchors(floors, subject):
    """Every anchor entry this subject's asset class obliges, in the
    order it is read: the anchorless common set, the class's own list,
    then the named product's conditional items. An anchored class
    contributes only its own list, which is empty - the four canonical
    tests are its anchor and they are checked separately."""
    registry = floors.get("asset_classes") or {}
    entry = registry.get(asset_class(subject))
    if entry is None:
        return []
    anchors = []
    if is_anchorless(subject):
        common = registry.get("common_anchorless") or {}
        anchors += list(common.get("anchors") or ())
    anchors += list(entry.get("anchors") or ())
    crypto = asset_class(subject) == "crypto"
    named = coin(subject, floors) if crypto else product(subject)
    product_entry = (entry.get("products") or {}).get(named) or {}
    rule = entry.get("monetary_coin_rule") or {}
    if crypto and subject.get("kind") not in rule.get("coin_kinds", ()):
        return anchors
    lifts = product_entry.get("class_anchors_lifted") or {}
    class_ids = {item.get("id") for item in entry.get("anchors") or ()
                 if item.get("kind") == "id"}
    if set(lifts) - class_ids:
        raise ValueError("the coin lifts an id absent from the class anchors: %s"
                         % sorted(set(lifts) - class_ids))
    anchors = [item for item in anchors if not (
        item.get("kind") == "id" and item.get("id") in lifts)]
    if crypto and subject.get("kind") in rule.get("coin_kinds", ()):
        anchors += coin_appended_anchors(floors, subject)
    else:
        anchors += list(product_entry.get("anchors") or ())
    return anchors
