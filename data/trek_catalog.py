import json
from urllib.parse import quote

from database import db
from models import Trek, CartItem, Order

def wiki_photo(filename, width=1400):
    """Wikimedia Commons image of a specific place, served at a sane width.
    Special:FilePath redirects to the current file, so these do not rot when a
    file is re-uploaded."""
    return (f"https://commons.wikimedia.org/wiki/Special:FilePath/"
            f"{quote(filename)}?width={width}")

PHOTOS = {
    "kudremukh": {
        "local": "/static/kudremukh.jpg",
        "remote": wiki_photo("Kudremukh National Park.jpg"),
        "gallery": [
            wiki_photo("Beautiful Kudremukha trek Buddha rock.jpg", 1000),
            wiki_photo("Shola Grasslands and forests in the Kudremukh National Park, Western Ghats, Karnataka.jpg", 1000),
            wiki_photo("Mountains of Kudremukh.jpg", 1000),
            wiki_photo("A view from South Kanara border in the Kudremukh National Park.jpg", 800),
            wiki_photo("Blue skies and green hills (23317241020).jpg", 800),
            wiki_photo("Leaving the peak behind. (22986181353).jpg", 800),
        ],
    },
    "kumara-parvatha": {
        "local": "/static/kumara-parvatha.jpg",
        "remote": wiki_photo("Kumara parvatha.jpg"),
        "gallery": [
            wiki_photo("Kumara Parvatha cliff.JPG", 1000),
            wiki_photo("This is the beautiful view of Kumara parvatha.jpg", 1000),
            wiki_photo("Kumara parvatha.jpg", 1000),
            wiki_photo("Trekking5.jpg", 800),
            wiki_photo("Trekking7.jpg", 800),
        ],
    },
    "savandurga": {
        "local": "/static/savandurga.png",
        "remote": wiki_photo("Savandurga Hill 01.jpg"),
        "gallery": [
            wiki_photo("On the way to Savandurga (3692301065).jpg", 1000),
            wiki_photo("Panhole Savandurga1.jpg", 1000),
            wiki_photo("Savandurga Hill 01.jpg", 1000),
            wiki_photo("Savandurga forest.jpg", 800),
            wiki_photo("Savandurga temple.jpg", 800),
            wiki_photo("Savandurga waterfall.jpg", 800),
        ],
    },
    "skandagiri": {
        "local": wiki_photo("Cloud over Skandagiri hills.jpg"),
        "remote": wiki_photo("Skandagiri Hills.jpg"),
        "gallery": [
            wiki_photo("Skandagiri hills top in Chikkaballapur district -1.jpg", 1000),
            wiki_photo("Skandagiri hills top in Chikkaballapur district -2.jpg", 1000),
            wiki_photo("Cloud over Skandagiri hills.jpg", 1000),
            wiki_photo("Skandagiri Trek Forest Reception Counter 3.jpg", 800),
            wiki_photo("Skandagiri Hills.jpg", 800),
        ],
    },
    "kodachadri": {
        "local": wiki_photo("Kodachadri hills.jpg"),
        "remote": wiki_photo("Kodachadri, Shivamogga, Karnataka, India 7366 (14186531550).jpg"),
        "gallery": [
            wiki_photo("Kodachadri, Shivamogga, Karnataka, India 7366 (14186531550).jpg", 1000),
            wiki_photo("Kodachadri hills.jpg", 1000),
            wiki_photo("Kodachadri.JPG", 1000),
            wiki_photo("Beautiful sights (49005366603).jpg", 800),
        ],
    },
    "nandi-hills-sunrise": {
        "local": wiki_photo("Nandi hills top view.jpg"),
        "remote": wiki_photo("Nandhi Hills.jpg"),
        "gallery": [
            wiki_photo("Nandi hills top view.jpg", 1000),
            wiki_photo("Nandhi Hills.jpg", 1000),
            wiki_photo("Nandi at Nandi Hills-1.jpg", 1000),
            wiki_photo("Enjoying the Beauty of Nandi hills in Wet Monsoon.jpg", 800),
            wiki_photo("Nehru Nilaya @ Nandi Hills.jpg", 800),
            wiki_photo("Ancient writings on the walls of a cave, Nandi Hills, Chikkaballapur, Karnataka (2014).jpg", 800),
        ],
    },
}

HERO_PHOTO = PHOTOS["kudremukh"]["remote"]


def seed_treks():
    treks = [
        Trek(
            slug="kudremukh", district="Chikkamagaluru", state="Karnataka", sort_order=1, featured=True,
            name="Kudremukh", location="Chikkamagaluru, Karnataka", region="Western Ghats",
            tagline="Twenty kilometres of rolling grassland and shola forest, ending on the horse-faced ridge.",
            description="Kudremukh is the classic Western Ghats grassland trek: a long, undulating walk through "
                        "shola pockets, three stream crossings and open ridge after open ridge, finishing on a "
                        "summit named for the horse-face profile it shows from the west.",
            long_description=(
                "The trail starts behind Mullodi village and climbs gently for the first hour through coffee and "
                "cardamom, before the canopy opens and the grassland takes over. From there it is exposed the whole "
                "way, which is exactly why the October to February window matters so much."
                "|| Distance is the real difficulty here rather than gradient. Twenty kilometres round trip on soft, "
                "tussocky ground works your ankles harder than a shorter, steeper climb would. Most groups take five "
                "to six hours up and four down."
                "|| The forest department caps daily entries and requires you to be off the trail well before dark, "
                "so we start at first light. That also buys you the best chance of a clear summit before the cloud "
                "builds up through the afternoon."),
            price=2449, difficulty="Moderate, long day on foot", difficulty_band="Moderate",
            duration="1 day", distance="20 km round trip", altitude="1,892 m",
            group_size="8 - 15 trekkers",
            starting_point="Mullodi village", ending_point="Kudremukh peak",
            best_season="October to February",
            how_to_reach="Mullodi is reached via Kalasa, roughly 330 km from Bengaluru and 130 km from Mangaluru. "
                         "Overnight buses run to Kalasa; from there it is a 12 km jeep ride on a rough track to the "
                         "homestay at Mullodi, which we arrange as part of the booking.",
            highlights="The horse-face profile from the final ridge; three stream crossings; shola forest pockets; "
                       "grassland that runs to the horizon; Lakya dam views on a clear day; sunrise from the second ridge",
            things_to_carry="Trekking shoes with deep tread; 3 litres of water; packed lunch and energy snacks; "
                            "rain shell even outside monsoon; sunscreen and a cap; personal medication; a walking stick if your knees prefer one",
            inclusions="Forest department entry and trekking permit; lead guide and sweep guide; homestay breakfast at Mullodi; "
                       "jeep transfer from Kalasa to Mullodi and back; first-aid support; waste bags for the group",
            exclusions="Travel from your city to Kalasa; lunch on the trail; personal gear and rain wear; "
                       "anything you buy in the village; travel insurance",
            safety_info="The grassland is fully exposed with no shade and no water source after the second stream, so "
                        "ration your water. After rain the black-soil sections turn greasy and the descent is where "
                        "most slips happen. Turnaround time is 1pm regardless of how close the summit looks.",
            permit_info="Trekking inside Kudremukh National Park needs a forest department permit, and daily entries "
                        "are capped. Carry a government photo ID; the name must match the booking. Camping is not "
                        "permitted anywhere inside the park.",
            itinerary=json.dumps([
                {"when": "Previous night", "title": "Reach Kalasa", "text": "Overnight bus from Bengaluru. We meet you at Kalasa and jeep across to the Mullodi homestay."},
                {"when": "6:00 am", "title": "Briefing and breakfast", "text": "Route brief, water check and a hot breakfast. Packed lunch goes into your bag here."},
                {"when": "6:45 am", "title": "Start the climb", "text": "Gentle plantation trail for the first hour, then out into the open grassland."},
                {"when": "9:30 am", "title": "Stream crossings", "text": "Three crossings in quick succession. Last reliable water point, so fill up here."},
                {"when": "12:00 pm", "title": "Summit", "text": "The final ridge walk and the horse-face view. Lunch at the top if the wind allows."},
                {"when": "1:00 pm", "title": "Turn around", "text": "Hard turnaround time. The descent is long and we want everyone down in daylight."},
                {"when": "5:00 pm", "title": "Back at Mullodi", "text": "Tea, a wash, and the jeep back to Kalasa for your onward bus."},
            ]),
            faqs=json.dumps([
                {"q": "Is this a good first trek?", "a": "Only if you already walk 8 to 10 km comfortably. The gradient is kind but the distance is not, and there is no short version once you are on the ridge."},
                {"q": "Are leeches a problem?", "a": "Between June and September, badly. In the October to February window you will rarely see one. Salt or Dettol on your socks handles the stragglers."},
                {"q": "Can I camp at the summit?", "a": "No. Camping is banned inside the national park and the forest department checks. We stay at the Mullodi homestay instead."},
                {"q": "What if the weather turns?", "a": "We call it 24 hours ahead. If the trail is unsafe you get a free date change or a full refund, your choice."},
            ]),
            gallery=json.dumps(PHOTOS["kudremukh"]["gallery"]),
            image_url=PHOTOS["kudremukh"]["local"], fallback_image=PHOTOS["kudremukh"]["remote"],
            rating=4.9, reviews_count=214,
        ),
        Trek(
            slug="kumara-parvatha", district="Dakshina Kannada", state="Karnataka", sort_order=2, featured=True,
            name="Kumara Parvatha", location="Kukke Subramanya, Karnataka", region="Western Ghats",
            tagline="Karnataka's hardest weekend climb: two days, three false summits and a night at Bhattara Mane.",
            description="A two-day climb from Kukke Subramanya through dense forest, a brutal open stretch known as "
                        "the Kallu Mantapa section, and a final push over Shesha Parvatha to the Kumara Parvatha summit.",
            long_description=(
                "There is a reason this one has a reputation. The first half is forest, steep and humid but shaded. "
                "Past Bhattara Mane the trees stop and the trail becomes a series of rock steps and grass slopes with "
                "the sun full on you, and the summit keeps hiding behind one more rise."
                "|| We break the climb with a night at Bhattara Mane, the forest house partway up where the family has "
                "been feeding trekkers for decades. Simple food, a floor to sleep on, and an early start the next day."
                "|| Come with some training behind you. If you can do a stair-climbing session and a 10 km walk in the "
                "same week without much complaint, you will enjoy this. If not, take Skandagiri first and come back."),
            price=2749, difficulty="Difficult, steep and sustained", difficulty_band="Difficult",
            duration="2 days", distance="28 km round trip", altitude="1,712 m",
            group_size="6 - 12 trekkers",
            starting_point="Kukke Subramanya", ending_point="Kumara Parvatha summit",
            best_season="October to February",
            how_to_reach="Kukke Subramanya is about 280 km from Bengaluru and 105 km from Mangaluru, with overnight "
                         "KSRTC buses running directly to the temple town. The trail head is a ten minute walk from "
                         "the bus stand.",
            highlights="Bhattara Mane, the forest house that feeds every trekker on the hill; Girigadde viewpoint; "
                       "the Shesha Parvatha false summit; sunrise above the cloud line; the Pushpagiri sanctuary forest; "
                       "views into Kodagu on a clear morning",
            things_to_carry="Broken-in trekking shoes, not new ones; 4 litres of water capacity; headlamp with spare "
                            "batteries; warm layer for the night; toilet paper and a trowel; electrolyte sachets; "
                            "a change of clothes for the second day",
            inclusions="Forest department permit and entry; lead guide and sweep guide; overnight stay and meals at "
                       "Bhattara Mane; dinner, breakfast and next-day packed lunch; first-aid support; waste bags",
            exclusions="Travel to and from Kukke Subramanya; lunch on day one; sleeping bag hire; personal gear; "
                       "temple darshan and any local expenses",
            safety_info="This is a physically demanding climb with a long committing section above the tree line. "
                        "Heat exhaustion is the most common problem we see, not falls. Drink before you are thirsty, "
                        "and tell the sweep guide early if you are struggling rather than at the top.",
            permit_info="Forest department permission is required and is arranged with your booking. Carry photo ID. "
                        "Camping on the summit is prohibited; the only permitted overnight stop is Bhattara Mane. "
                        "Plastic is checked at the forest gate.",
            itinerary=json.dumps([
                {"when": "Day 1, 7:00 am", "title": "Meet at Kukke", "text": "Breakfast in town, gear check and the forest gate formalities."},
                {"when": "Day 1, 8:30 am", "title": "Into the forest", "text": "Steep, shaded and humid. Slow and steady pace to Bhattara Mane."},
                {"when": "Day 1, 1:00 pm", "title": "Bhattara Mane", "text": "Lunch, rest, and an easy afternoon. Optional walk up to Girigadde for the evening view."},
                {"when": "Day 1, 8:00 pm", "title": "Dinner and lights out", "text": "Home-cooked meal and an early night on the floor. Bring your own bedding roll."},
                {"when": "Day 2, 4:30 am", "title": "Summit push", "text": "Headlamps on. Kallu Mantapa, then Shesha Parvatha, then the real summit."},
                {"when": "Day 2, 7:30 am", "title": "Sunrise at the top", "text": "Above the cloud line on a good morning, with Kodagu spread out to the north."},
                {"when": "Day 2, 3:00 pm", "title": "Back in Kukke", "text": "Long descent, a wash, and buses back to the city."},
            ]),
            faqs=json.dumps([
                {"q": "How fit do I need to be?", "a": "Fitter than for anything else on this site. Six to eight hours of climbing on day one and an early summit push on day two, both with a pack."},
                {"q": "What are the toilets like?", "a": "Basic at Bhattara Mane and nothing at all above it. Carry toilet paper and a trowel, and bury everything well off the trail."},
                {"q": "Can I do it in one day?", "a": "Experienced trekkers do, but we do not run it that way. The two-day version is safer and you actually get to enjoy the top."},
                {"q": "Is there mobile signal?", "a": "Patchy at Bhattara Mane, nothing on the climb. Tell someone at home your schedule before you start."},
            ]),
            gallery=json.dumps(PHOTOS["kumara-parvatha"]["gallery"]),
            image_url=PHOTOS["kumara-parvatha"]["local"], fallback_image=PHOTOS["kumara-parvatha"]["remote"],
            rating=4.8, reviews_count=176,
        ),
        Trek(
            slug="savandurga", district="Ramanagara", state="Karnataka", sort_order=3, featured=True,
            name="Savandurga", location="Magadi, Ramanagara", region="Deccan plateau",
            tagline="One of Asia's largest monoliths, climbed straight up bare rock in under three hours.",
            description="A short, steep scramble up an enormous granite dome an hour from Bengaluru, past the ruins "
                        "of a Kempegowda-era fort to a summit with the entire Ramanagara countryside laid out below.",
            long_description=(
                "Savandurga is deceptive. Four and a half kilometres sounds like nothing, and then you are on open "
                "rock at a gradient that has you using your hands, with white paint marks as the only trail."
                "|| The grip of your shoes matters more here than on any other trail we run. The granite is excellent "
                "when dry and genuinely dangerous when wet, which is why we do not run this one in the monsoon at all."
                "|| Because it is close to the city we start very early, summit by sunrise and are back down before "
                "the rock heats up. In summer the surface temperature at 10am is high enough to be unpleasant through "
                "thin soles."),
            price=849, difficulty="Difficult, steep exposed rock", difficulty_band="Difficult",
            duration="3 hours up and down", distance="4.5 km round trip", altitude="1,226 m",
            group_size="8 - 15 trekkers",
            starting_point="Bettada Dari trail head", ending_point="Kempegowda fort summit",
            best_season="October to February",
            how_to_reach="Savandurga is 55 km from Bengaluru via Magadi Road, about 90 minutes by car. Buses run to "
                         "Magadi, with autos covering the last 12 km. Most groups leave the city at 4am to be on the "
                         "rock before sunrise.",
            highlights="Sunrise from the summit with Manchanabele reservoir below; Kempegowda fort ruins; the Nandi "
                       "shrine near the top; vulture nesting cliffs on the far face; a genuine rock scramble within "
                       "an hour of the city",
            things_to_carry="Shoes with soft, grippy soles, not hiking boots with hard treads; 2 litres of water; "
                            "a light breakfast to eat at the top; cap and sunscreen; a small daypack that does not swing",
            inclusions="Eco-tourism entry fee; lead guide and sweep guide; pre-climb briefing on the rock section; "
                       "first-aid support; waste bags for the group",
            exclusions="Transport from Bengaluru; food and water; personal gear; anything at the base village",
            safety_info="The exposed rock section is the crux and it is unforgiving in the wet, so we cancel rather "
                        "than run it after rain. Keep three points of contact on the steep slabs, descend facing the "
                        "rock where the angle is high, and do not wander towards the edges for photographs.",
            permit_info="Savandurga has an official Karnataka eco-tourism trail with a gate fee and fixed opening "
                        "hours. Entry closes in the early afternoon and the trail must be cleared by evening.",
            itinerary=json.dumps([
                {"when": "4:00 am", "title": "Leave Bengaluru", "text": "Pickup from a central point. Coffee stop on Magadi Road."},
                {"when": "5:30 am", "title": "Base and briefing", "text": "Gate formalities, shoe check and a short talk about the rock section."},
                {"when": "5:45 am", "title": "Start climbing", "text": "Scrub and boulders at first, then straight onto open granite following the white marks."},
                {"when": "7:00 am", "title": "Summit and sunrise", "text": "Fort ruins, the Nandi shrine and breakfast with the reservoir below."},
                {"when": "8:15 am", "title": "Descend", "text": "Slower than the climb. We take the steep slabs one at a time as a group."},
                {"when": "10:00 am", "title": "Back in the city", "text": "Down before the rock gets hot, home before lunch."},
            ]),
            faqs=json.dumps([
                {"q": "Why is a 4.5 km trek graded difficult?", "a": "Because of the angle and the exposure, not the distance. Long stretches are bare rock steep enough to need your hands."},
                {"q": "Can beginners do it?", "a": "Fit beginners with no fear of heights, yes. If exposure bothers you, Skandagiri or Nandi Hills is the better call."},
                {"q": "What shoes should I wear?", "a": "Running shoes with soft rubber grip better on granite than stiff hiking boots. Worn-smooth soles are the single biggest risk."},
                {"q": "Do you run it in the monsoon?", "a": "No. Wet granite here is genuinely dangerous and we do not take the chance."},
            ]),
            gallery=json.dumps(PHOTOS["savandurga"]["gallery"]),
            image_url=PHOTOS["savandurga"]["local"], fallback_image=PHOTOS["savandurga"]["remote"],
            rating=4.7, reviews_count=308,
        ),
        Trek(
            slug="skandagiri", district="Chikkaballapur", state="Karnataka", sort_order=4,
            name="Skandagiri", location="Chikkaballapur, Karnataka", region="Deccan plateau",
            tagline="A night climb to a ruined fort, timed so you reach the top as the cloud sea lights up.",
            description="Also called Kalavara Durga, Skandagiri is the classic Bengaluru night trek: a moderate "
                        "torch-lit climb through scrub and boulders to a Tipu-era fort, arriving in time for sunrise "
                        "over a valley that fills with cloud in winter.",
            long_description=(
                "The appeal is the timing. You start around 2am, climb by headlamp with the lights of Chikkaballapur "
                "behind you, and reach the fort walls while it is still dark. Then the valley below turns white and "
                "the sun comes up through it."
                "|| The trail itself is straightforward: a defined path, some loose rock, a few short scrambles near "
                "the top. What catches people out is doing it on no sleep, in the dark, in the cold."
                "|| Winter is when the cloud inversion actually happens. Outside December to February you still get a "
                "fine sunrise, just without the sea of cloud that Skandagiri is known for."),
            price=1049, difficulty="Moderate, night climb", difficulty_band="Moderate",
            duration="5 hours, overnight start", distance="8 km round trip", altitude="1,450 m",
            group_size="8 - 15 trekkers",
            starting_point="Papagni Mutt, Chikkaballapur", ending_point="Skandagiri fort ruins",
            best_season="December to February",
            how_to_reach="Chikkaballapur is 60 km north of Bengaluru on NH44, about 75 minutes by road. The trail "
                         "head at Papagni Mutt is a further 15 minutes from town on a narrow village road.",
            highlights="The winter cloud inversion at sunrise; Tipu-era fort walls and cisterns; climbing entirely by "
                       "headlamp; Nandi Hills visible across the valley; a small temple at the summit",
            things_to_carry="Headlamp, not a phone torch; warm layer and a windproof top; 2 litres of water; snacks "
                            "for the summit wait; shoes with grip for loose gravel; a light blanket if you feel the cold",
            inclusions="Forest department night entry permit; lead guide and sweep guide; hot tea at the summit; "
                       "first-aid support; waste bags for the group",
            exclusions="Transport from Bengaluru; breakfast; headlamp hire; personal warm layers",
            safety_info="Night climbing means the main risks are a twisted ankle on loose rock and getting separated "
                        "from the group. Stay between the two guides, keep your light on the ground rather than in "
                        "people's eyes, and it gets cold and windy at the top while you wait for sunrise.",
            permit_info="Night trekking here requires forest department permission and is only allowed with a "
                        "registered operator. Entry is checked at the base and headcounts are taken both ways.",
            itinerary=json.dumps([
                {"when": "11:30 pm", "title": "Leave Bengaluru", "text": "Pickup from a central point, drive up NH44."},
                {"when": "1:30 am", "title": "Base check", "text": "Permit formalities, headlamp check and a briefing on staying together in the dark."},
                {"when": "2:00 am", "title": "Start climbing", "text": "Scrub and boulder trail by torchlight, with a couple of short scrambles near the fort."},
                {"when": "4:30 am", "title": "Reach the fort", "text": "Find a sheltered spot behind the walls, layer up and wait. Hot tea comes out here."},
                {"when": "6:15 am", "title": "Sunrise", "text": "The valley fills with cloud on a good winter morning and the sun comes up through it."},
                {"when": "9:00 am", "title": "Back at the base", "text": "Descend in daylight, which is a completely different trail to the one you climbed."},
            ]),
            faqs=json.dumps([
                {"q": "Will I definitely see the cloud sea?", "a": "No, and anyone promising it is lying. It needs cold, still, humid winter mornings. December to February gives you the best odds."},
                {"q": "Is a phone torch enough?", "a": "No. You need both hands free on the scramble sections. A proper headlamp is required, not optional."},
                {"q": "How cold does it get?", "a": "Single digits at the summit in December and January, with wind. People underestimate the wait between arriving and sunrise."},
                {"q": "Can I sleep at the top?", "a": "Overnight camping is not permitted. The climb is timed so the wait is about ninety minutes."},
            ]),
            gallery=json.dumps(PHOTOS["skandagiri"]["gallery"]),
            image_url=PHOTOS["skandagiri"]["local"], fallback_image=PHOTOS["skandagiri"]["remote"],
            rating=4.6, reviews_count=241,
        ),
        Trek(
            slug="kodachadri", district="Shivamogga", state="Karnataka", sort_order=5,
            name="Kodachadri", location="Shivamogga, Karnataka", region="Western Ghats",
            tagline="Ghat forest, an old iron pillar on a grassy summit, and the sea visible on a clear evening.",
            description="A shola and grassland climb inside the Mookambika wildlife sanctuary, finishing at the "
                        "Sarvajna Peetha shrine and an iron pillar that has stood on the summit for centuries, with "
                        "the Arabian Sea on the horizon.",
            long_description=(
                "Kodachadri sits right at the western edge of the Ghats, which is why the view is different from "
                "anything else on this list. On a clear evening you can pick out the coastline from the top."
                "|| The trail climbs through thick evergreen forest before opening into grassland for the last stretch. "
                "There is a jeep track that goes most of the way, which we ignore; the walking route through the forest "
                "is the whole point."
                "|| Hidlumane falls sits just off the trail and is worth the short detour outside the driest months. "
                "It is a scramble over wet rock, so it is optional and we go in small groups."),
            price=2349, difficulty="Moderate, steady forest climb", difficulty_band="Moderate",
            duration="1 day", distance="14 km round trip", altitude="1,343 m",
            group_size="8 - 14 trekkers",
            starting_point="Nittur base village", ending_point="Sarvajna Peetha, Kodachadri summit",
            best_season="October to February",
            how_to_reach="Nittur is near Kollur in Shivamogga district, roughly 400 km from Bengaluru. Overnight buses "
                         "run to Kollur, and the base village is 20 km further by local jeep, which we arrange.",
            highlights="Hidlumane falls on the lower trail; the iron pillar at Sarvajna Peetha; the Arabian Sea on the "
                       "horizon at sunset; evergreen shola forest; Mookambika sanctuary birdlife; grassland ridge walking",
            things_to_carry="Trekking shoes that handle wet rock; 3 litres of water; packed lunch; rain shell; "
                            "quick-dry clothes if you plan to do the falls; sunscreen; personal medication",
            inclusions="Sanctuary entry and trekking permit; lead guide and sweep guide; jeep transfer from Kollur to "
                       "Nittur and back; breakfast at the base; first-aid support; waste bags",
            exclusions="Travel to and from Kollur; lunch; accommodation before or after; personal gear",
            safety_info="The Hidlumane falls detour is over slick rock and is the most common place for injuries on "
                        "this trail, so it is optional and guided in small groups. Above the tree line the wind picks "
                        "up sharply in the evening. Leeches are common on the forest section after any rain.",
            permit_info="Kodachadri lies inside the Mookambika wildlife sanctuary and needs a forest department entry "
                        "permit, arranged with your booking. Plastic is checked at the gate and camping inside the "
                        "sanctuary is not allowed.",
            itinerary=json.dumps([
                {"when": "Previous night", "title": "Bus to Kollur", "text": "Overnight from Bengaluru. We meet you at Kollur in the morning."},
                {"when": "7:00 am", "title": "Breakfast at Nittur", "text": "Jeep transfer to the base village, breakfast and the sanctuary gate formalities."},
                {"when": "8:00 am", "title": "Into the forest", "text": "Steady climb through evergreen forest, thick canopy and stream crossings."},
                {"when": "10:00 am", "title": "Hidlumane falls", "text": "Optional detour in small groups. Wet rock scramble, worth it outside the dry months."},
                {"when": "12:30 pm", "title": "Grassland and summit", "text": "Out of the trees and along the ridge to the iron pillar and the shrine."},
                {"when": "2:00 pm", "title": "Start down", "text": "Same route back through the forest, slower on the wet sections."},
                {"when": "5:30 pm", "title": "Back at Nittur", "text": "Tea, jeep to Kollur, and the evening bus home."},
            ]),
            faqs=json.dumps([
                {"q": "Can I just take the jeep up?", "a": "Jeeps run to near the summit, but then it is a drive, not a trek. Our booking is for the walking route."},
                {"q": "Are leeches bad here?", "a": "In and just after the monsoon, yes. Anti-leech socks or salt on your ankles handles it. By December they are mostly gone."},
                {"q": "Can we swim at the falls?", "a": "A dip in the lower pool when the flow is gentle, under guide supervision. Not in high flow, and never alone."},
                {"q": "Will I actually see the sea?", "a": "On a clear, dry-season evening, usually. In haze or cloud, no. It is a bonus rather than the reason to come."},
            ]),
            gallery=json.dumps(PHOTOS["kodachadri"]["gallery"]),
            image_url=PHOTOS["kodachadri"]["local"], fallback_image=PHOTOS["kodachadri"]["remote"],
            rating=4.8, reviews_count=132,
        ),
        Trek(
            slug="nandi-hills-sunrise", district="Chikkaballapur", state="Karnataka", sort_order=6,
            name="Nandi Hills sunrise walk", location="Chikkaballapur, Karnataka", region="Deccan plateau",
            tagline="The gentlest trail we run: 1,200 stone steps, a summer palace at the top, home by breakfast.",
            description="A short stepped climb up the old Nandi Betta path to Tipu Sultan's summer retreat, built for "
                        "people who want a sunrise and a view without a five-hour day on their legs.",
            long_description=(
                "This is the one we send first-timers, families and anyone coming back from a break in training. The "
                "route is a maintained stone stairway with handrails on the exposed sections, and there is a road to "
                "the top if anyone needs to bail out."
                "|| It is still an early start and still 1,200 steps, so it is not nothing. But you can be at the top "
                "for sunrise and back in Bengaluru before most people have had breakfast."
                "|| The summit has the summer palace, Tipu's Drop, a working temple and a cafe, which makes it a good "
                "place to actually sit for an hour rather than turn straight around."),
            price=649, difficulty="Easy, stepped path throughout", difficulty_band="Easy",
            duration="2.5 hours", distance="6 km round trip", altitude="1,478 m",
            group_size="8 - 20 trekkers",
            starting_point="Nandi Hills base, Sultanpet gate", ending_point="Tipu's summer palace, summit",
            best_season="All year, best from October to February",
            how_to_reach="Nandi Hills is 60 km from Bengaluru off NH44, about an hour by road. The stepped trail "
                         "starts near the Sultanpet gate at the base, separate from the vehicle road to the top.",
            highlights="Sunrise over the plateau; Tipu Sultan's summer palace; the Bhoga Nandeeshwara temple at the "
                       "base; Tipu's Drop viewpoint; paragliders launching on clear mornings; a summit cafe",
            things_to_carry="Any comfortable walking shoes; 1.5 litres of water; a light jacket for the summit wind; "
                            "sunscreen; a camera if you care about the sunrise",
            inclusions="Entry fee at the gate; lead guide and sweep guide; a guided walk of the summit ruins; "
                       "first-aid support; waste bags",
            exclusions="Transport from Bengaluru; breakfast at the summit cafe; personal gear",
            safety_info="The steps are well maintained but get slippery in the early morning dew, so take the descent "
                        "at a sensible pace. The summit edges near Tipu's Drop are unfenced in places and people take "
                        "risks there for photographs. Stay back from the drop.",
            permit_info="No trekking permit is needed. There is a standard entry fee at the gate, included in your "
                        "booking, and the hill has fixed opening hours enforced by the horticulture department.",
            itinerary=json.dumps([
                {"when": "4:30 am", "title": "Leave Bengaluru", "text": "Pickup from a central point and a straight run up NH44."},
                {"when": "5:45 am", "title": "Base gate", "text": "Entry formalities at Sultanpet and a short briefing at the foot of the steps."},
                {"when": "6:00 am", "title": "Climb the steps", "text": "Roughly 1,200 stone steps at an easy pace, with two rest points on the way."},
                {"when": "6:45 am", "title": "Sunrise at the top", "text": "Find a spot on the eastern edge before the crowd arrives from the road."},
                {"when": "7:30 am", "title": "Walk the summit", "text": "Summer palace, temple and Tipu's Drop, with the history behind each."},
                {"when": "9:30 am", "title": "Back in the city", "text": "Down the same steps and home before the day starts."},
            ]),
            faqs=json.dumps([
                {"q": "Can children do this?", "a": "Yes. Kids from about seven upwards manage the steps fine at a slow pace, and the road option exists if anyone tires."},
                {"q": "Is it very crowded?", "a": "The summit gets busy once the road traffic arrives around 7am. Climbing the steps early puts you up there well before that."},
                {"q": "What if I cannot finish the steps?", "a": "Tell the sweep guide. The vehicle road runs parallel and we can get you to the top or the base without drama."},
                {"q": "Is this enough training for the harder treks?", "a": "It is a good start. Do this comfortably, then Skandagiri or Kudremukh, and then think about Kumara Parvatha."},
            ]),
            gallery=json.dumps(PHOTOS["nandi-hills-sunrise"]["gallery"]),
            image_url=PHOTOS["nandi-hills-sunrise"]["local"], fallback_image=PHOTOS["nandi-hills-sunrise"]["remote"],
            rating=4.5, reviews_count=389,
        ),
    ]
    db.session.add_all(treks)
    db.session.commit()
    print(f"[DB] Seeded {len(treks)} treks.")


TREK_CODES = {
    "kudremukh": "KUD",
    "kumara-parvatha": "KPV",
    "savandurga": "SAV",
    "skandagiri": "SKN",
    "kodachadri": "KOD",
    "nandi-hills-sunrise": "NAN",
}


