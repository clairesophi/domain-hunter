import os
import re
import math
import socket
import random
import itertools
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple, Any

import requests
from flask import Flask, render_template, request, jsonify

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
app = Flask(__name__, template_folder=TEMPLATE_DIR)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

WHOISXMLAPI_KEY = os.getenv("WHOISXMLAPI_KEY", "")
WHOISXMLAPI_ENDPOINT = "https://domain-availability.whoisxmlapi.com/api/v1"

# Free WHOIS replacement: RDAP (Registration Data Access Protocol) — operated by
# ICANN and the TLD registries directly. No API key, no signup, no per-call cost.
# We hit the registry servers directly (fast: ~80–170ms) instead of going through
# rdap.org's bootstrap proxy, which adds a redirect hop and times out under load.
RDAP_REGISTRIES = {
    "com": "https://rdap.verisign.com/com/v1/domain/",
    "net": "https://rdap.verisign.com/net/v1/domain/",
    # Identity Digital runs the RDAP server for many gTLDs we care about.
    "io":       "https://rdap.identitydigital.services/rdap/domain/",
    "studio":   "https://rdap.identitydigital.services/rdap/domain/",
    "training": "https://rdap.identitydigital.services/rdap/domain/",
    "design":   "https://rdap.identitydigital.services/rdap/domain/",
    "house":    "https://rdap.identitydigital.services/rdap/domain/",
    "school":   "https://rdap.identitydigital.services/rdap/domain/",
}
RDAP_BOOTSTRAP = "https://rdap.org/domain/"
USE_RDAP = os.getenv("USE_RDAP", "1") != "0"

# .ai has no widely-available public RDAP. Use DNS as a heuristic fallback:
# if the domain resolves we mark it taken; if NXDOMAIN we mark it available.
# Imperfect for parked / NS-only domains, but a reasonable signal.
TLDS_NEEDING_DNS_FALLBACK = {"ai"}


def rdap_url_for(domain: str) -> str:
    tld = domain.rsplit(".", 1)[-1].lower() if "." in domain else ""
    base = RDAP_REGISTRIES.get(tld, RDAP_BOOTSTRAP)
    return base + domain

MAX_CHECKS_HARD_LIMIT = int(os.getenv("MAX_CHECKS_HARD_LIMIT", "180"))
DOMAIN_CHECK_WORKERS = int(os.getenv("DOMAIN_CHECK_WORKERS", "12"))
# How many candidates to check per visible result (oversample so we have a deep
# enough pool of *available* domains to randomly sample from for each rerun).
OVERSAMPLE_FACTOR = int(os.getenv("OVERSAMPLE_FACTOR", "4"))

STOPWORDS = set("""
the and for with from this that into onto your our you they them their a an of to in on at by or as is are be being been we create turn new ways things stronger possible raw material something highly refined ai
like just really kinda very much more less some any all not but its also has have had get got make made take taken give given quite rather such than then there here when where while what which who whom whose through about across along around because before behind beneath beside besides between beyond down inside near off out over since throughout toward under until upon within without
""".split())

BASE_VOCAB = """
refinery refine refined refining polish polished burnish cut facet multifacet lapidary lapis alembic crucible kiln silica glass prism crystal quartz mineral stone quarry foundry forge grain alloy matter material mediasmith smith craft crafted atelier precision exacting whiteglove premium signal transformation transmute distill distillery distillation carat gemstone gem oxide pigment surface texture

scaffold structure structural support supported framework infrastructure future practice applied futures fluent formwork trellis plumb line plumbline workflow workflows system systems architecture rail bridge backbone rig method standard protocol platform enablement enable tooling lattice latticework manifold manyfold spline hairspring plane column beam grid matrix

superpower advantage hidden capability access magic leverage acceleration edge secret mission wonder practical practicalwonder machine hand machinehand kindling current undercurrent round corner roundcorner blacklabel black label whiteglove unlocked unlock powered power ability fluent force spark charge booster turbo lift

alchemy connection connective flow translation translate interoperability transmission relay latent latent space latentspace manifold manyfold lattice glue roux caustic radiance liminal emergent viable ascendant ephemeral channel conduit signal link connect weave bridge mesh node orbit field current resonance synthesize synthesis synapse circuit feedback network protocol exchange transform transmutation

toolbox tool tools toolkit kit almanac keyring tackle box tacklebox jig pattern cut spec cutspec workbench cabinet instrument instruments method workflow playbook template engine production studio lab labs works platform creative advantage creativeadvantage curated collection module console stack library shelf bench drawer

garden gardener gardening grow growth growing cultivate cultivation cultivar seed seedling sprout bloom blossom bud root roots branch leaf foliage canopy orchard greenhouse hothouse glasshouse nursery botany botanical horticulture photosynthesis chlorophyll fertile fertility soil compost mulch humus loam vine ripen ripening harvest perennial heirloom propagate graft prune pollen petal stamen rhizome trellis arbor arbour hedgerow meadow pasture verdant evergreen tendril germinate

current currents flow flowing flux energy energetic electric electrical electricity charge charged voltage circuit conduit wire wiring spark sparks surge pulse pulsing rhythm wave waveform frequency oscillate oscillation resonance resonate vibration vibrate kinetic momentum dynamo turbine generator power powered grid lightning thunder static field magnetic magnet magnetism plasma kindle ignite ignition ember embers glow incandescent luminous radiant radiate beam ray current undertow tide tidal stream river ripple eddy whirl spiral vortex

marble granite basalt obsidian jade opal amber coral pearl ivory brass copper bronze tin pewter platinum mica feldspar slate flint agate onyx ruby sapphire emerald topaz garnet turquoise malachite alabaster soapstone schist sandstone limestone shale chalk pumice chert rhyolite gneiss phyllite tuff lodestone meteorite obsidian flintstone

creek brook eddy whirlpool cascade waterfall mist fog dew frost ember cinder smoke vapor steam plume nimbus cumulus cirrus stratus haze gloaming dusk dawn twilight gloam aurora halo corona

bellows anvil chisel awl plane vise lathe mortar pestle sieve sifter retort still thurible censer alembic distillation rectification cohobation calcination sublimation precipitation filtration decantation reagent solvent crucible mordant

xylem phloem cambium pollen pollinate germination propagation grafting layering espalier topiary parterre hedgerow heirloom orchard windbreak coppice spinney thicket bramble briar bracken thatch

scriptorium codex herbarium menagerie aviary apothecary archive observatory vitrine atrium portico colonnade rotunda cupola arcade cloister loggia oratory belfry campanile

threshold undertone overtone harmonic cadence tempo throb thrum drone tremor shudder shimmer flicker flutter waver glimmer luster sheen gloss patina verdigris tarnish weather wear

ferment tincture mordant pigment glaze enamel lacquer varnish gilding inlay marquetry intarsia mosaic tessera cabochon intaglio cameo bezel filigree damascene

river ocean sea marsh meadow valley ridge summit glacier tide harbor cove inlet headland bluff isle archipelago lagoon fjord oasis savanna tundra taiga prairie delta estuary canyon gorge ravine plateau highland lowland bayou

storm breeze gust drizzle downpour blizzard hail sleet squall gale calm zephyr tempest monsoon cyclone whirlwind

lantern beacon glow flicker flash spark glimmer shine lustre sheen shimmer halo aurora daybreak nightfall starlight moonlight sunlight firelight torchlight candlelight

chime hum drone peal knell toll melody harmony cadence refrain chant song echo whisper murmur lullaby ballad sonnet hymn

silk velvet linen suede leather wax satin gauze muslin tweed canvas burlap denim cotton wool felt twill brocade

heron hawk owl raven eagle fox otter lynx fawn hare deer stag salmon trout oyster whale dolphin sparrow swan crane finch nightingale crow magpie kingfisher dove hummingbird

vessel vase urn chalice bowl basin jar jug flask vial ampoule retort kettle cauldron carafe decanter pitcher amphora ewer

gateway doorway window threshold hearth alcove niche cloister courtyard balcony parapet cornice gable archway hall chamber room antechamber vestibule foyer

dawn dusk twilight daybreak nightfall hour season era epoch moment instant interval span

drift glide flow spin turn twirl swirl dance wave bend curve arc loop coil

keep vault library cabinet drawer shelf chest trunk locker safe

bloom blossom flourish thrive rest slumber repose dwell linger settle alight

weave thread knot braid lattice mesh web net rope cord twine string ribbon banner pennant

moss lichen fern frond palm vine ivy willow oak maple birch cedar cypress pine spruce juniper laurel olive fig pomegranate

ash dust sand pebble gravel cobble shard fragment grain mote speck flake

ledger journal scroll tablet page ink quill brush palette canvas easel album notebook compendium volume tome anthology

honey beeswax resin amber sap nectar pollen syrup balm myrrh frankincense sandalwood

needle pin spindle bobbin reel spool shuttle thread thimble awl scissors shears

bell carillon harp lute lyre flute reed pipe horn drum cymbal gong tabor

field garden grove orchard vineyard hedge thicket copse bower glade clearing

stone pebble brick tile tile slate shingle thatch beam rafter joist column post pillar

shell husk hull rind peel skin scale feather wing tail fin claw horn antler tusk

vow oath pledge bond covenant accord pact troth banner signet seal token relic emblem

key lock latch hinge bolt clasp buckle button stud nail rivet stitch seam

trail trailhead campsite cabin cottage lodge bungalow boathouse boatyard meadow grove thicket clearing bluff knoll hill mound dune shore beach reef shoal pier dock wharf marina harbor bay gulf landing crossing junction

kitchen pantry larder cellar attic loft parlor study den porch deck patio veranda terrace courtyard yard backyard frontroom commonroom

bread loaf crust crumb butter cheese jam preserve pickle relish broth soup stew brew tea infusion mead cider wine sauce marinade rind zest peel

hand finger palm wrist eye gaze glance vision sight ear voice tongue tooth bone spine sinew nerve marrow

calm peace stillness quiet hush serenity grace ease comfort warmth coolness focus clarity balance steadiness gravity weight

morning daybreak sunrise noon afternoon nightfall midnight evening sundown starlight earlybird earlymorning lateday

journey trek hike path route course passage crossing bridge ford pass gateway compass map atlas itinerary

fire flame ember spark blaze candle wick lamp torch lantern firefly bonfire campfire furnace hearth oven stove

song tune chord note rhythm beat hum echo whisper anthem chant chorus refrain ballad lullaby

house home cabin cottage lodge hut tent pavilion barn stable workshop studio gallery pavilion booth kiosk

hammer chisel awl plane saw drill brush paint glue tape nail bolt rivet thread needle pin clamp ruler tape

wood metal clay paper cloth fabric leather rope cord twine silk wool cotton linen velvet denim hemp jute

tree flower leaf grass bush vine root branch twig bud sprout seedling sapling thicket undergrowth

sun rain snow wind hail cloud thunder lightning rainbow shower drizzle puddle pond

fox owl raven hawk hare deer stag salmon trout bee butterfly moth wren swallow lark robin warbler

bottle jar box crate barrel basket pouch satchel pack pouch knapsack rucksack tote duffel

sail row paddle drift float glide soar dive leap jump climb hike walk wander roam stroll amble ramble

glow gleam shine sparkle luster shimmer brightness warmth coolness clarity vibrancy

maker builder mender tinker cooper smith weaver carver potter wright wheelwright shipwright blacksmith goldsmith silversmith

market bazaar fair festival gathering parade picnic retreat summit assembly meetup workshop residency

chapter page tale story fable legend myth ballad sonnet stanza verse poem essay manuscript

school class lesson study scholar tutor mentor master apprentice journeyman protege fellow

orchestra choir band ensemble quintet quartet trio duet solo overture prelude finale

game play sport race match contest quest puzzle riddle mystery clue trail breadcrumb hint

scent aroma flavor savor touch caress sense feeling impression

lift uplift focus clarity balance harmony radiance vitality

dawn morning twilight evening dusk sundown sunset

oak elm ash maple birch fir spruce pine cedar willow hawthorn hazel rowan

salt sugar honey spice pepper ginger mint sage thyme basil rosemary lavender chamomile

silver gold bronze brass iron tin steel pewter

stream brook river creek pond lake bay shore tide wave

cloud mist haze fog dew frost rime sleet

home garden workshop atelier studio library archive gallery museum theatre

friend host guest stranger neighbor companion fellow comrade ally

dream memory wonder echo trace footprint hint signal beacon

cup mug bowl plate dish saucer pitcher kettle teapot

forefront frontier vanguard helm prow leading axon neuron dendrite synapse signal transmission broadcast channel antenna beacon pulse rhythm waveform wavelength tuning resonance frequency emission tone hum echo

blade edge sword spear arrow dagger sabre point tip cutting precision sharp acuity warrior sentinel guardian scout ranger herald envoy knight forge forging

clubhouse lodge hideaway retreat refuge sanctuary haven shelter den firepit camp campfire bonfire hearth fellowship fellowship guild member members company gathering circle salon supper feast

ascension ascent climb summit rise momentum traction thrust drive propulsion continuum spectrum gradient arc trajectory horizon

empowerment agency autonomy mastery craft mentorship guidance partnership alliance accord pact covenant trust

philosophy ethos creed doctrine manifesto principle stance vision foresight insight intuition

revision iteration draft refinement polish overhaul rework redo

ruckus fracas tumult kerfuffle uproar commotion stir buzz

ego persona guise mask alter dual mirror reflection echo

disciple acolyte devotee novice apprentice fellow protege

concierge steward host helmsman captain pilot navigator

patch mend repair fix splice darn

mascot emblem token totem banner pennant standard signet seal

stillwave undercurrent ripple eddy whirlpool surge wash spray spume foam

forefront tip helm prow point edge spear vanguard ascendant

inner core depth marrow heart center essence kernel pith
""".split()

BRAND_PHRASES = [
    "Lapidary", "Lapis", "LAPIS", "Alembic", "Mediasmiths", "Crucible", "Kiln",
    "Silica Works", "Signal Quarry", "Crystal Logic", "The Grain Foundry", "Multifacet",
    "Mattercraft", "Sand to Signal", "Stone Signal", "Future Practice", "Applied Futures",
    "Working Futures", "Future Fluent", "Trellis", "Formwork", "Plumb Line", "Manifold",
    "Manyfold", "Spline", "Latticework", "Hairspring", "Plane", "Round Corner",
    "Working Magic", "Practical Wonder", "Machine Hand", "Under Current", "Kindling",
    "Post Standard", "White Glove Black Label", "Summer Camp", "Secret Mission",
    "Magic Touch", "Transmission", "Relay", "Latent Space", "Splinetime", "Permascope",
    "Caustic", "Radiance", "Ephemeral", "Liminal", "Emergent", "Ascendant", "Viable",
    "New Glue", "Roux", "Goblinworks", "Tortoiseworks", "FMRL", "LUCA",
    "Creative Advantage", "Almanac", "Keyring", "Tackle Box", "Icebox", "JigWorks",
    "Cut to Spec", "Signal Works", "Pattern Works", "JJNC",
    # From the team call brief — words the team is already gravitating toward.
    "Stillwave", "UltraHuman", "Forefront", "Axon", "Clubhouse", "Ruckus",
    "Continuum", "Ascension", "Momentum", "Forging", "Patches", "Philosophy",
    "Revision", "Liquid", "Disciple", "Concierge", "Quickfix", "Members Only",
    "The Campfire", "Supper Club", "Inner Signal", "Secret Weapon",
    "Halt and Catch Fire", "Alter Ego", "Inner Voice", "Signal to Noise",
    "Tip of the Sword", "Leading Edge", "White Glove", "Top of the Game",
    "First Impression", "Secret Society"
]

PRIMARY_SUFFIXES = ["works", "studio", "labs", "lab", "studios"]
# Evocative, not SaaS-y. Avoid "tools/systems/platform/engine/method" which read tech-y.
SECONDARY_SUFFIXES = [
    "foundry", "atelier", "practice", "office", "house", "school",
    "society", "guild", "circle", "salon", "room", "table", "group", "co"
]
SUFFIXES = PRIMARY_SUFFIXES + SECONDARY_SUFFIXES

# Category-specific affixes. Used sparingly (1–2 per seed, random pick each run)
# so brand names like "permascope" or "wildgrove" or "metaframe" surface
# without flooding the pool.
THEMATIC_PREFIXES = {
    "refinery":   ["ultra", "micro", "omni", "pan"],
    "scaffold":   ["meta", "proto", "multi", "infra"],
    "superpower": ["omni", "hyper", "perma", "supra"],
    "alchemy":    ["trans", "meta", "neo", "perma"],
    "toolbox":    ["multi", "omni", "perma", "pan"],
    "garden":     ["ever", "wild", "semi", "neo"],
    "current":    ["perma", "omni", "super", "ultra"],
    "signal":     ["meta", "omni", "hyper", "trans"],
    "edge":       ["ultra", "hyper", "omni", "supra"],
    "campfire":   ["ever", "neo", "pan", "omni"],
}
THEMATIC_SUFFIXES = {
    "refinery":   ["scope", "smith", "wright"],
    "scaffold":   ["form", "way", "side", "gate"],
    "superpower": ["scope", "force", "edge"],
    "alchemy":    ["scope", "blend", "flux"],
    "toolbox":    ["smith", "wright", "shop", "kit"],
    "garden":     ["side", "grove", "land", "plot"],
    "current":    ["wave", "surge", "scope", "flux"],
    "signal":     ["scope", "wave", "tone", "beacon"],
    "edge":       ["edge", "scope", "force", "tip"],
    "campfire":   ["house", "club", "lodge", "salon", "circle"],
}

# Words we don't want to surface in generated names — too tech-y or generic for
# a non-AI/non-digital brand.
BLOCKED_WORDS = {
    "ai", "digital", "tech", "technology", "data", "algorithm", "algo",
    "neural", "smart", "app", "apps", "cyber", "virtual", "online",
    "compute", "code", "dev", "saas", "cloud", "blockchain", "crypto",
    "platform", "system", "systems", "tool", "tools", "software", "ml"
}

BRANCHES = {
    "refinery": (
        "refinery refine polish polished burnish lapidary stone crystal quarry foundry "
        "raw material craft precision gem facet marble granite pearl alabaster basalt "
        "distill distillation alembic crucible kiln chisel anvil mineral pigment ore"
    ),
    "scaffold": (
        "scaffold structure structural framework support beam column trellis lattice "
        "infrastructure foundation pillar plank rafter joist platform standard method "
        "blueprint architecture bridge backbone formwork rig grid matrix"
    ),
    "superpower": (
        "superpower advantage capability magic spark force kindling power lift uplift "
        "courage might strength talent ability charisma leverage edge hidden unlock "
        "boost charge spark ignite kindle catalyst breakthrough"
    ),
    "alchemy": (
        "alchemy distill transmute infusion brew ferment tincture mordant potion "
        "concoction blend mix transform translate connect link bridge synthesis "
        "synapse circuit conduit relay weave glue catalyst emergent flow"
    ),
    "toolbox": (
        "toolbox tool tools toolkit kit workbench bench workshop maker craft "
        "hammer chisel awl plane saw drill brush vise clamp ruler lathe jig "
        "handle wrench screwdriver shelf drawer cabinet stack equipment instrument "
        "kit playbook template apparatus"
    ),
    "garden": (
        "garden gardening grow growth cultivate seed seedling sprout bloom blossom "
        "orchard greenhouse nursery botany horticulture soil root harvest dew rain "
        "petal stamen pollen pollinate fertile compost prune trellis vine flower "
        "hedge meadow grove arbor bouquet bud bramble"
    ),
    "current": (
        "current currents flow flowing energy electricity charge voltage circuit "
        "pulse wave frequency kinetic dynamo spark surge resonance river stream tide "
        "ocean ripple eddy waterfall cascade thunder lightning storm wind rain "
        "vortex whirlpool drift breeze gale tempest"
    ),
    "signal": (
        "signal signals transmission broadcast channel antenna beacon frequency "
        "wavelength tuning resonance pulse rhythm waveform tone hum emission echo "
        "relay carrier dispatch communicate clarity inner signal undercurrent"
    ),
    "edge": (
        "edge blade tip point forefront frontier vanguard helm prow leading sword "
        "spear arrow dagger sabre weapon warrior sharp acuity precision cutting "
        "forward first ahead pioneer scout cutting-edge"
    ),
    "campfire": (
        "campfire hearth lodge club clubhouse circle gathering supper salon "
        "fellowship guild member members retreat refuge den fire firepit log "
        "kindling ember warmth company conversation companions secret society"
    ),
}


def slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def tokenize(text: str) -> List[str]:
    out = []
    for word in re.split(r"[^a-zA-Z0-9]+", text.lower()):
        word = slugify(word)
        if len(word) >= 3 and word not in STOPWORDS:
            out.append(word)
    return list(dict.fromkeys(out))


def cosine(a: Tuple[float, ...], b: Tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def get_openai_client() -> OpenAI:
    if not OPENAI_API_KEY:
        raise RuntimeError("Missing OPENAI_API_KEY environment variable.")
    if OpenAI is None:
        raise RuntimeError("The openai package is not installed.")
    return OpenAI(api_key=OPENAI_API_KEY)


def embed_batch(texts: List[str]) -> Dict[str, Tuple[float, ...]]:
    unique = list(dict.fromkeys(t for t in texts if t))
    if not unique:
        return {}
    client = get_openai_client()
    response = client.embeddings.create(
        model=OPENAI_EMBEDDING_MODEL,
        input=unique
    )
    return {text: tuple(item.embedding) for text, item in zip(unique, response.data)}


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/api/tree", methods=["POST"])
def api_tree():
    body = request.get_json(force=True)
    concepts = body.get("concepts", "")
    top_words_n = int(body.get("topWords", 60))

    if not concepts.strip():
        return jsonify({"error": "Type some concepts first."}), 400

    try:
        user_words = tokenize(concepts)
        phrase_words = []
        for phrase in BRAND_PHRASES:
            phrase_words.extend(tokenize(phrase))
            phrase_words.append(slugify(phrase))

        vocab = list(dict.fromkeys([*BASE_VOCAB, *phrase_words, *user_words]))
        vocab = [word for word in vocab if 3 <= len(word) <= 18]

        to_embed = [concepts, *vocab, *BRANCHES.values()]
        vectors = embed_batch(to_embed)
        concept_vec = vectors[concepts]

        scored = [
            {"word": word, "score": cosine(concept_vec, vectors[word])}
            for word in vocab
        ]
        scored.sort(key=lambda item: item["score"], reverse=True)
        top = scored[:top_words_n]

        branch_out = []
        for name, desc in BRANCHES.items():
            branch_vec = vectors[desc]

            # (a) Score every vocab word against THIS branch description,
            #     independent of the prompt. Gives us each branch's full
            #     "semantic neighborhood" — needed for wildcards below.
            all_branch_scored = sorted(
                [{"word": w, "score": cosine(branch_vec, vectors[w])} for w in vocab],
                key=lambda x: x["score"],
                reverse=True,
            )

            # (b) Main picks: top branch-relevant words from inside the
            #     top-N prompt-related list — these are the "obvious" matches.
            main_terms = sorted(
                [
                    {"word": item["word"], "score": cosine(branch_vec, vectors[item["word"]])}
                    for item in top
                ],
                key=lambda item: item["score"],
                reverse=True,
            )[:17]
            main_words = {t["word"] for t in main_terms}

            # (c) Wildcards: random picks from the tight top of the branch's
            #     own ranking — high enough on the list to still feel on-theme,
            #     skipping anything already in main. Each rebuild reshuffles
            #     so you get different on-theme surprises per click.
            wildcard_pool = [
                t for t in all_branch_scored[:35]
                if t["word"] not in main_words
            ]
            n_wildcards = min(3, len(wildcard_pool))
            wildcards = random.sample(wildcard_pool, n_wildcards) if wildcard_pool else []
            for w in wildcards:
                w["wildcard"] = True

            branch_out.append({
                "name": name,
                "score": cosine(concept_vec, branch_vec),
                "terms": main_terms + wildcards,
            })

        branch_out.sort(key=lambda item: item["score"], reverse=True)

        return jsonify({
            "top_words": top,
            "branches": branch_out,
            "user_words": user_words,  # non-filler words from the user's prompt
        })

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


MAX_NAME_LEN = 16  # tighter cap — keeps compounds readable as brand names


def _to_singular(word: str) -> str:
    """Best-effort singularizer for English plurals (gems → gem, studios → studio)."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("es") and word[-3] in "sxz" + "ch":
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _looks_readable(slug: str) -> bool:
    """Reject names with awkward consonant runs, repeats, or junk."""
    if len(slug) < 3 or len(slug) > MAX_NAME_LEN:
        return False
    # 3+ same letter in a row (e.g. "ssss" or "aaa")
    if re.search(r"(.)\1{2,}", slug):
        return False
    # 5+ consonants in a row — unpronounceable
    if re.search(r"[bcdfghjklmnpqrstvwxz]{5,}", slug):
        return False
    return True


def _has_blocked_chunk(slug: str, parts: List[str]) -> bool:
    """True if any explicit part-of-a-compound is on the blocklist."""
    if slug in BLOCKED_WORDS:
        return True
    return any(p in BLOCKED_WORDS for p in parts)


def candidates_from_words(
    seeds: List[str],
    partners: List[str],
    include_studio: bool,
    include_compounds: bool,
    tlds: List[str],
    max_checks: int,
    active_branches: List[str] = None,
) -> List[Dict[str, str]]:
    """Generate domain candidates from seed words tethered by branch partners.

    `seeds` are the words the user explicitly picked.
    `partners` are other words from the same branch(es) those seeds came from —
    they keep compounds semantically anchored ("gem" + "facet" → "gemfacet"
    rather than "gem" + some random word).
    `tlds` is a list like ["com", "ai", "studio"]. Each accepted slug is
    expanded into one candidate per TLD.
    """
    max_checks = min(max_checks, MAX_CHECKS_HARD_LIMIT)

    seed_slugs = [slugify(w) for w in seeds if slugify(w)]
    seed_slugs = [_to_singular(s) for s in seed_slugs if s not in BLOCKED_WORDS]
    seed_slugs = list(dict.fromkeys(seed_slugs))

    partner_slugs = [slugify(w) for w in partners if slugify(w)]
    partner_slugs = [_to_singular(p) for p in partner_slugs if p not in BLOCKED_WORDS]
    partner_slugs = list(dict.fromkeys(p for p in partner_slugs if p and p not in seed_slugs))

    ordered: List[Tuple[str, str]] = []
    seen = set()

    def add(name: str, source: str, parts: List[str] = None):
        cleaned = slugify(name)
        if cleaned in seen:
            return
        if not _looks_readable(cleaned):
            return
        if _has_blocked_chunk(cleaned, parts or [cleaned]):
            return
        # Skip plural variants if the singular form is already in the pool
        # (gemstones rejected if gemstone is there).
        singular = _to_singular(cleaned)
        if singular != cleaned and singular in seen:
            return
        ordered.append((cleaned, source))
        seen.add(cleaned)

    def fuses(a: str, b: str) -> bool:
        return a == b or a in b or b in a

    # 1. Seeds themselves (always single concepts)
    for w in seed_slugs:
        add(w, "seed", [w])

    # 2. Seed + primary suffix (gem + works → gemworks) — 2 concepts
    if include_studio:
        for w in seed_slugs:
            for suf in PRIMARY_SUFFIXES:
                if w != suf:
                    add(w + suf, f"+{suf}", [w, suf])

    # 3. Seed × partner — both orders, interleaved (gemfacet, facetgem) — 2 concepts
    if include_compounds:
        for partner in partner_slugs:
            for seed in seed_slugs:
                if fuses(seed, partner):
                    continue
                add(seed + partner, f"{seed} + {partner}", [seed, partner])
                add(partner + seed, f"{partner} + {seed}", [partner, seed])

    # 4. Seed × seed (when user picked multiple seeds) — 2 concepts
    if include_compounds and len(seed_slugs) > 1:
        for first, second in itertools.permutations(seed_slugs, 2):
            if fuses(first, second):
                continue
            add(first + second, "compound", [first, second])

    # 5. Partner standalones (top ~10) — surfaces strong branch words alone
    for partner in partner_slugs[:10]:
        add(partner, "branch context", [partner])

    # 6. Partner + primary suffix (facetworks, multifacetstudio) — 2 concepts
    if include_studio:
        for partner in partner_slugs[:10]:
            for suf in PRIMARY_SUFFIXES:
                if partner != suf:
                    add(partner + suf, f"{partner}+{suf}", [partner, suf])

    # 7. Seed + secondary suffix (atelier, foundry, house, salon, …) — 2 concepts
    if include_studio:
        for w in seed_slugs:
            for suf in SECONDARY_SUFFIXES:
                if w != suf:
                    add(w + suf, f"+{suf}", [w, suf])

    # 8. Thematic affixes — category-specific prefixes/suffixes used sparingly.
    #    Pull from the categories the user has actively selected from. Picks
    #    1–2 random affixes per seed each run so they reshuffle on Rerun.
    branches = active_branches or []
    pre_pool, suf_pool = [], []
    for b in branches:
        pre_pool.extend(THEMATIC_PREFIXES.get(b, []))
        suf_pool.extend(THEMATIC_SUFFIXES.get(b, []))
    pre_pool = list(dict.fromkeys(pre_pool))
    suf_pool = list(dict.fromkeys(suf_pool))

    if pre_pool:
        for w in seed_slugs:
            picks = random.sample(pre_pool, min(2, len(pre_pool)))
            for pre in picks:
                add(pre + w, f"{pre}+", [pre, w])
    if suf_pool:
        for w in seed_slugs:
            picks = random.sample(suf_pool, min(2, len(suf_pool)))
            for suf in picks:
                add(w + suf, f"+{suf}", [w, suf])

    # Expand each slug into one row per TLD
    tlds = [t.lstrip(".").lower() for t in tlds if t]
    if not tlds:
        tlds = ["com"]

    rows = []
    for name, source in ordered:
        for tld in tlds:
            rows.append({"domain": f"{name}.{tld}", "source": source})

    # Random sample so each check shows a different cross-section of the pool.
    # Seed rows always appear; everything else is sampled. Hitting "Rerun"
    # gets a fresh sample without rebuilding the tree.
    seed_rows = [r for r in rows if r["source"] == "seed"]
    other_rows = [r for r in rows if r["source"] != "seed"]
    remaining = max(0, max_checks - len(seed_rows))
    if remaining and other_rows:
        sampled = random.sample(other_rows, min(remaining, len(other_rows)))
    else:
        sampled = []
    return seed_rows + sampled


def check_domain_dns(domain: str) -> Dict[str, Any]:
    """Heuristic fallback for TLDs without reliable public RDAP (e.g. .ai).
    Resolves taken if DNS resolves, available if NXDOMAIN.
    """
    try:
        socket.setdefaulttimeout(6)
        socket.gethostbyname(domain)
        return {"domain": domain, "status": "taken", "available": False,
                "reason": "dns lookup (best effort)"}
    except socket.gaierror:
        # NXDOMAIN or no A record. Most registered domains have at least an A
        # record; flag as available with caveat.
        return {"domain": domain, "status": "available", "available": True,
                "reason": "dns lookup (best effort — verify manually)"}
    except Exception as exc:
        return {"domain": domain, "status": "unknown", "available": False, "reason": str(exc)}


def check_domain_rdap(domain: str) -> Dict[str, Any]:
    """Free, no-key WHOIS replacement.

    RDAP returns 404 when a domain is not in the registry (= available)
    and 200 with JSON metadata when it is registered (= taken).
    """
    tld = domain.rsplit(".", 1)[-1].lower() if "." in domain else ""
    if tld in TLDS_NEEDING_DNS_FALLBACK:
        return check_domain_dns(domain)

    try:
        response = requests.get(
            rdap_url_for(domain),
            timeout=10,
            allow_redirects=True,
            headers={"Accept": "application/rdap+json"},
        )
    except requests.RequestException as exc:
        return {"domain": domain, "status": "error", "available": False, "reason": str(exc)}

    code = response.status_code
    if code == 404:
        return {"domain": domain, "status": "available", "available": True}
    if code == 200:
        return {"domain": domain, "status": "taken", "available": False}
    if code == 429:
        return {"domain": domain, "status": "error", "available": False,
                "reason": "rate limited — slow down or check fewer at once"}
    if code in (400, 422):
        return {"domain": domain, "status": "error", "available": False,
                "reason": f"invalid domain (HTTP {code})"}
    return {"domain": domain, "status": "unknown", "available": False,
            "reason": f"HTTP {code}"}


def check_domain_whoisxmlapi(domain: str) -> Dict[str, Any]:
    params = {
        "apiKey": WHOISXMLAPI_KEY,
        "domainName": domain,
        "outputFormat": "JSON"
    }

    try:
        response = requests.get(WHOISXMLAPI_ENDPOINT, params=params, timeout=12)
    except requests.RequestException as exc:
        return {"domain": domain, "status": "error", "available": False, "reason": str(exc)}

    if response.status_code != 200:
        return {
            "domain": domain,
            "status": "error",
            "available": False,
            "reason": f"HTTP {response.status_code}: {response.text[:160]}"
        }

    data = response.json()
    info = data.get("DomainInfo", data)
    raw = str(
        info.get("domainAvailability")
        or info.get("availability")
        or info.get("status")
        or ""
    ).lower()

    available_values = {"available", "1", "true", "yes"}
    taken_values = {"unavailable", "registered", "taken", "0", "false", "no"}

    if raw in available_values:
        return {"domain": domain, "status": "available", "available": True}
    if raw in taken_values:
        return {"domain": domain, "status": "taken", "available": False}
    return {"domain": domain, "status": "unknown", "available": False}


def check_domain(domain: str) -> Dict[str, Any]:
    if USE_RDAP or not WHOISXMLAPI_KEY:
        return check_domain_rdap(domain)
    return check_domain_whoisxmlapi(domain)


@app.route("/api/check", methods=["POST"])
def api_check():
    body = request.get_json(force=True)
    words = body.get("words", [])
    partners = body.get("compoundPartners", [])
    active_branches = body.get("activeBranches", [])
    include_studio = bool(body.get("includeStudio", False))
    include_compounds = bool(body.get("includeCompounds", True))
    tlds = body.get("tlds") or ["com"]
    # Back-compat: old clients may still send includeIo
    if body.get("includeIo") and "io" not in tlds:
        tlds = [*tlds, "io"]
    show_taken = bool(body.get("showTaken", False))
    max_checks = int(body.get("maxChecks", 30))

    if not words:
        return jsonify({"error": "Pick at least one word from the tree first."}), 400

    # If the client didn't send branch context, fall back to pairing seeds with
    # each other (the old behavior).
    if not partners:
        partners = words

    # Oversample the candidate pool so we have a chance of finding `max_checks`
    # available domains (not just any domains). User picks "max=40" → check up
    # to ~160 candidates → return up to 40 that are actually available.
    check_budget = min(max_checks * OVERSAMPLE_FACTOR, MAX_CHECKS_HARD_LIMIT)
    candidates = candidates_from_words(
        words, partners, include_studio, include_compounds, tlds, check_budget,
        active_branches=active_branches,
    )

    if not candidates:
        return jsonify({"candidates": [], "results": []})

    domain_to_source = {c["domain"]: c["source"] for c in candidates}
    domains = [c["domain"] for c in candidates]

    with ThreadPoolExecutor(max_workers=DOMAIN_CHECK_WORKERS) as pool:
        checked_list = list(pool.map(check_domain, domains))

    for checked in checked_list:
        checked["source"] = domain_to_source.get(checked["domain"], "")

    available = [r for r in checked_list if r.get("available")]
    taken_or_unknown = [r for r in checked_list if not r.get("available")]

    # Random sample down to user's max so each rerun surfaces different ones.
    if len(available) > max_checks:
        random.shuffle(available)
        sampled = available[:max_checks]
    else:
        sampled = available

    if show_taken:
        # When showing taken, also throw in a few non-available for context.
        extra = max(0, max_checks - len(sampled))
        if extra and taken_or_unknown:
            random.shuffle(taken_or_unknown)
            sampled = sampled + taken_or_unknown[:extra]

    sampled.sort(key=lambda r: (not r.get("available"), r["domain"]))

    return jsonify({
        "candidates": candidates,
        "results": sampled,
        "stats": {
            "checked": len(checked_list),
            "available_total": len(available),
            "shown": len(sampled),
        },
        "provider": "rdap" if (USE_RDAP or not WHOISXMLAPI_KEY) else "whoisxmlapi"
    })


if __name__ == "__main__":
    app.run(debug=True, port=int(os.getenv("PORT", "5050")))
