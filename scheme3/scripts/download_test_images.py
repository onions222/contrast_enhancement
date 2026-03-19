from __future__ import annotations

import json
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ce_scheme3.dataset_manifest_builder import build_manifest_entries, export_manifest_csv
from ce_scheme3.public_eval_subset import build_public_eval_subset


RAW_ROOT = REPO_ROOT / "data" / "raw" / "wikimedia_commons"
MANIFEST_DIR = REPO_ROOT / "data" / "derived" / "manifests"
CURATED_MANIFEST_PATH = MANIFEST_DIR / "2026-03-17-wikimedia_commons_manifest.csv"
CURATED_METADATA_PATH = RAW_ROOT / "2026-03-17-wikimedia_commons_curated.json"


@dataclass(frozen=True)
class DownloadSpec:
    filename: str
    commons_file_name: str
    source_page: str
    notes: str
    expected_bucket: str
    expected_failure_modes: tuple[str, ...]
    width: int = 1600


DOWNLOAD_SPECS = (
    DownloadSpec(
        filename="high_key_empty_apartment_room_window.jpg",
        commons_file_name="Empty Apartment Room Window.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Empty_Apartment_Room_Window.jpg",
        notes="High-key bright interior with white wall and window, useful for highlight washout checks.",
        expected_bucket="high_key",
        expected_failure_modes=("highlight_washout", "over_enhancement"),
    ),
    DownloadSpec(
        filename="high_key_bright_modern_kitchen.jpg",
        commons_file_name="USVI IMG 5159 - Bright modern kitchen with white cabinets a central island and pendant lights under a vaulted ceiling.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:USVI_IMG_5159_-_Bright_modern_kitchen_with_white_cabinets_a_central_island_and_pendant_lights_under_a_vaulted_ceiling.jpg",
        notes="High-key modern kitchen interior with bright cabinets and ceiling for highlight handling checks.",
        expected_bucket="high_key",
        expected_failure_modes=("highlight_washout", "over_enhancement"),
    ),
    DownloadSpec(
        filename="high_key_bright_living_room_white_furniture.jpg",
        commons_file_name="EFTA00001567 - Bright living room with white furniture a colorful tropical rug and a large TV under a vaulted ceiling.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:EFTA00001567_-_Bright_living_room_with_white_furniture_a_colorful_tropical_rug_and_a_large_TV_under_a_vaulted_ceiling.jpg",
        notes="High-key living room with bright walls and white furniture for highlight washout and over-lift checks.",
        expected_bucket="high_key",
        expected_failure_modes=("highlight_washout", "over_enhancement"),
    ),
    DownloadSpec(
        filename="high_key_bright_sunlit_room_large_windows.jpg",
        commons_file_name="EFTA00003020-Beach-House - Bright sunlit room with large windows overlooking the ocean featuring a white sofa computer desk and a view of the sea.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:EFTA00003020-Beach-House_-_Bright_sunlit_room_with_large_windows_overlooking_the_ocean_featuring_a_white_sofa_computer_desk_and_a_view_of_the_sea.jpg",
        notes="High-key sunlit room with large windows and bright sea view for aggressive highlight handling checks.",
        expected_bucket="high_key",
        expected_failure_modes=("highlight_washout", "over_enhancement"),
    ),
    DownloadSpec(
        filename="high_key_bright_blue_painted_room_large_windows.jpg",
        commons_file_name="EFTA00003015-Beach-House - Bright blue-painted room with white walls and dark tiled floors featuring a desk setup wicker furniture and large windows overlooking a green landscape.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:EFTA00003015-Beach-House_-_Bright_blue-painted_room_with_white_walls_and_dark_tiled_floors_featuring_a_desk_setup_wicker_furniture_and_large_windows_overlooking_a_green_landscape.jpg",
        notes="High-key bright room with white walls and large windows for highlight washout and midtone preservation checks.",
        expected_bucket="high_key",
        expected_failure_modes=("highlight_washout", "over_enhancement"),
    ),
    DownloadSpec(
        filename="high_key_bright_room_cluttered_office_desk.jpg",
        commons_file_name="EFTA00003072-Beach-House - Cluttered office desk with papers files and a computer monitor in a bright room with a wicker couch and large windows.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:EFTA00003072-Beach-House_-_Cluttered_office_desk_with_papers_files_and_a_computer_monitor_in_a_bright_room_with_a_wicker_couch_and_large_windows.jpg",
        notes="High-key bright room with desk clutter to check highlight handling without washing out midtone detail.",
        expected_bucket="high_key",
        expected_failure_modes=("highlight_washout", "over_enhancement"),
    ),
    DownloadSpec(
        filename="high_key_sunlit_room.jpg",
        commons_file_name="Sunlit room.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Sunlit_room.jpg",
        notes="High-key sunlit interior for white-wall and bright-window highlight retention checks.",
        expected_bucket="high_key",
        expected_failure_modes=("highlight_washout", "over_enhancement"),
    ),
    DownloadSpec(
        filename="high_key_augustinerlesesaal_wien.jpg",
        commons_file_name="Augustinerlesesaal Wien 01.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Augustinerlesesaal_Wien_01.jpg",
        notes="Bright reading room with architectural detail for high-key texture and midtone preservation checks.",
        expected_bucket="high_key",
        expected_failure_modes=("highlight_washout", "over_enhancement"),
    ),
    DownloadSpec(
        filename="normal_biela_street_daytime.jpg",
        commons_file_name="Biela street in Košice (daytime).jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Biela_street_in_Ko%C5%A1ice_(daytime).jpg",
        notes="Normal daylight street scene with buildings, pavement, and moderate contrast.",
        expected_bucket="normal",
        expected_failure_modes=("general_quality_regression",),
    ),
    DownloadSpec(
        filename="normal_city_park_afternoon.png",
        commons_file_name="City park in the afternoon.png",
        source_page="https://commons.wikimedia.org/wiki/File:City_park_in_the_afternoon.png",
        notes="Normal outdoor park scene with foliage and medium contrast for balanced-case behavior.",
        expected_bucket="normal",
        expected_failure_modes=("general_quality_regression", "over_enhancement"),
    ),
    DownloadSpec(
        filename="normal_interior_kitchen.jpg",
        commons_file_name="Interior Kitchen.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Interior_Kitchen.jpg",
        notes="Normal indoor kitchen scene with ordinary mid-tones and object diversity.",
        expected_bucket="normal",
        expected_failure_modes=("general_quality_regression",),
    ),
    DownloadSpec(
        filename="normal_living_room.jpg",
        commons_file_name="Living Room.JPG",
        source_page="https://commons.wikimedia.org/wiki/File:Living_Room.JPG",
        notes="Normal indoor living-room scene for everyday mid-tone behavior.",
        expected_bucket="normal",
        expected_failure_modes=("general_quality_regression",),
    ),
    DownloadSpec(
        filename="normal_beijing_hotel_room_1.jpg",
        commons_file_name="Normal room in Beijing Hotel (20150822151850).JPG",
        source_page="https://commons.wikimedia.org/wiki/File:Normal_room_in_Beijing_Hotel_(20150822151850).JPG",
        notes="Neutral hotel-room interior with ordinary furniture and midtone balance.",
        expected_bucket="normal",
        expected_failure_modes=("general_quality_regression",),
    ),
    DownloadSpec(
        filename="normal_beijing_hotel_room_2.jpg",
        commons_file_name="Normal room in Beijing Hotel (20150822151853).JPG",
        source_page="https://commons.wikimedia.org/wiki/File:Normal_room_in_Beijing_Hotel_(20150822151853).JPG",
        notes="Neutral hotel-room interior under balanced exposure for scene-classification sanity checks.",
        expected_bucket="normal",
        expected_failure_modes=("general_quality_regression",),
    ),
    DownloadSpec(
        filename="normal_drafting_room_erb.jpg",
        commons_file_name="Interior View of Drafting Room in ERB - GPN-2000-001447.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Interior_View_of_Drafting_Room_in_ERB_-_GPN-2000-001447.jpg",
        notes="Midtone-dominant technical workspace scene for normal-bucket coverage.",
        expected_bucket="normal",
        expected_failure_modes=("general_quality_regression",),
    ),
    DownloadSpec(
        filename="normal_nyc_public_library_research_room.jpg",
        commons_file_name="NYC Public Library Research Room Jan 2006-1- 3.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:NYC_Public_Library_Research_Room_Jan_2006-1-_3.jpg",
        notes="Balanced indoor reading-room scene with distributed highlights and shadows.",
        expected_bucket="normal",
        expected_failure_modes=("general_quality_regression",),
    ),
    DownloadSpec(
        filename="normal_beijing_hotel_room_3.jpg",
        commons_file_name="Normal room in Beijing Hotel (20150822151912).JPG",
        source_page="https://commons.wikimedia.org/wiki/File:Normal_room_in_Beijing_Hotel_(20150822151912).JPG",
        notes="Backup neutral hotel-room sample for ordinary indoor exposure coverage.",
        expected_bucket="normal",
        expected_failure_modes=("general_quality_regression",),
    ),
    DownloadSpec(
        filename="low_key_empty_room_unsplash.jpg",
        commons_file_name="Empty Room (Unsplash).jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Empty_Room_(Unsplash).jpg",
        notes="Dark hallway and desk scene, useful for low-light detail lift and noise side-effect checks.",
        expected_bucket="low_key",
        expected_failure_modes=("shadow_crush", "noise_boost"),
    ),
    DownloadSpec(
        filename="low_key_vietnam_street_at_night.jpg",
        commons_file_name="Vietnam Street At Night.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Vietnam_Street_At_Night.jpg",
        notes="Low-key night street scene with practical lights and darker surroundings.",
        expected_bucket="low_key",
        expected_failure_modes=("shadow_crush", "noise_boost", "highlight_bloom"),
    ),
    DownloadSpec(
        filename="low_key_lamp_in_dark_room.jpg",
        commons_file_name="Lamp in dark room.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Lamp_in_dark_room.jpg",
        notes="Dark room with a single lamp for low-key detail and highlight control checks.",
        expected_bucket="low_key",
        expected_failure_modes=("shadow_crush", "highlight_bloom"),
    ),
    DownloadSpec(
        filename="low_light_noisy_dark_room_night_mode_off.jpg",
        commons_file_name="Dark room with street light shining through window (night mode off).jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Dark_room_with_street_light_shining_through_window_(night_mode_off).jpg",
        notes="Smartphone low-light capture with night mode off, useful for noise amplification and dark-detail lift checks.",
        expected_bucket="low_light_noisy",
        expected_failure_modes=("noise_boost", "shadow_crush", "middle_gray_lift_error"),
    ),
    DownloadSpec(
        filename="low_light_noisy_room_during_repair.jpg",
        commons_file_name="Low light room during repair.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Low_light_room_during_repair.jpg",
        notes="Real low-light interior with dark structure and practical light for noise boost and shadow-detail checks.",
        expected_bucket="low_light_noisy",
        expected_failure_modes=("noise_boost", "shadow_crush", "middle_gray_lift_error"),
    ),
    DownloadSpec(
        filename="low_key_dark_interior_light_pollution.jpg",
        commons_file_name="Dark interior with texterior light pollution.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Dark_interior_with_texterior_light_pollution.jpg",
        notes="Low-key interior with subtle dark detail and bright exterior spill for difficult shadow-detail behavior.",
        expected_bucket="low_key",
        expected_failure_modes=("shadow_crush", "halo", "highlight_bloom"),
    ),
    DownloadSpec(
        filename="low_key_reception_lounge_blue_hour_laos.jpg",
        commons_file_name="Reception lounge at Amantaka luxury Resort & Hotel at blue hour in Luang Prabang Laos.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Reception_lounge_at_Amantaka_luxury_Resort_%26_Hotel_at_blue_hour_in_Luang_Prabang_Laos.jpg",
        notes="Blue-hour interior with dark wood and local bright sources for low-key detail retention checks.",
        expected_bucket="low_key",
        expected_failure_modes=("shadow_crush", "halo", "middle_gray_lift_error"),
    ),
    DownloadSpec(
        filename="low_key_lobby_lounge_amantaka_suite_laos.jpg",
        commons_file_name="Lobby lounge of Amantaka Suite Amantaka luxury Resort & Hotel Luang Prabang Laos.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Lobby_lounge_of_Amantaka_Suite_Amantaka_luxury_Resort_%26_Hotel_Luang_Prabang_Laos.jpg",
        notes="Dim lounge interior with localized light sources for low-key detail retention and halo checks.",
        expected_bucket="low_key",
        expected_failure_modes=("shadow_crush", "halo", "middle_gray_lift_error"),
    ),
    DownloadSpec(
        filename="low_key_restaurant_room_amantaka_laos.jpg",
        commons_file_name="Restaurant room of Amantaka luxury Resort & Hotel in Luang Prabang Laos.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Restaurant_room_of_Amantaka_luxury_Resort_%26_Hotel_in_Luang_Prabang_Laos.jpg",
        notes="Dark structured interior with warm local lighting for low-key detail preservation checks.",
        expected_bucket="low_key",
        expected_failure_modes=("shadow_crush", "halo", "middle_gray_lift_error"),
    ),
    DownloadSpec(
        filename="low_key_fashion_walk_corridor_01.jpg",
        commons_file_name="HK CWB Fashion Walk interior corridor lobby 01.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:HK_CWB_Fashion_Walk_interior_corridor_lobby_01.jpg",
        notes="Dim corridor interior with local bright spots and textured mid-grays.",
        expected_bucket="low_key",
        expected_failure_modes=("shadow_crush", "halo"),
    ),
    DownloadSpec(
        filename="low_key_fashion_walk_corridor_02.jpg",
        commons_file_name="HK CWB Fashion Walk interior corridor lobby 02.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:HK_CWB_Fashion_Walk_interior_corridor_lobby_02.jpg",
        notes="Dark corridor interior with practical lights for low-key transition and local-contrast checks.",
        expected_bucket="low_key",
        expected_failure_modes=("shadow_crush", "halo"),
    ),
    DownloadSpec(
        filename="low_key_central_tower_lift_lobby_night.jpg",
        commons_file_name="HK Central night 中匯大廈 Central Tower lift lobby hall interior Aug-2010.JPG",
        source_page="https://commons.wikimedia.org/wiki/File:HK_Central_night_%E4%B8%AD%E5%8C%AF%E5%A4%A7%E5%BB%88_Central_Tower_lift_lobby_hall_interior_Aug-2010.JPG",
        notes="Night interior lift lobby with dark structure and reflected highlights.",
        expected_bucket="low_key",
        expected_failure_modes=("shadow_crush", "halo", "highlight_bloom"),
    ),
    DownloadSpec(
        filename="low_key_ball_room_central_night.jpg",
        commons_file_name="HK Robinson Road 31 ball room interior Central night Oct-2010.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:HK_Robinson_Road_31_ball_room_interior_Central_night_Oct-2010.jpg",
        notes="Dark ballroom interior with warm highlights and shadowed seating.",
        expected_bucket="low_key",
        expected_failure_modes=("shadow_crush", "middle_gray_lift_error"),
    ),
    DownloadSpec(
        filename="low_key_polyclinic_waiting_room_night.jpg",
        commons_file_name="HK Sai Ying Pun Jockey Club Polyclinic waiting room interior night Out Patient Payment Kiosk Sept-2012.JPG",
        source_page="https://commons.wikimedia.org/wiki/File:HK_Sai_Ying_Pun_Jockey_Club_Polyclinic_waiting_room_interior_night_Out_Patient_Payment_Kiosk_Sept-2012.JPG",
        notes="Night waiting-room interior with dark seating and localized bright kiosk elements.",
        expected_bucket="low_key",
        expected_failure_modes=("shadow_crush", "halo", "highlight_bloom"),
    ),
    DownloadSpec(
        filename="low_key_kwun_tong_swimming_pool_changing_room_night.jpg",
        commons_file_name="HK new Kwun Tong Swimming Pool changing room interior 觀塘游泳池 night Dec-2013.JPG",
        source_page="https://commons.wikimedia.org/wiki/File:HK_new_Kwun_Tong_Swimming_Pool_changing_room_interior_%E8%A7%80%E5%A1%98%E6%B8%B8%E6%B3%B3%E6%B1%A0_night_Dec-2013.JPG",
        notes="Low-key changing-room interior with broad dark regions and fluorescent highlights.",
        expected_bucket="low_key",
        expected_failure_modes=("shadow_crush", "middle_gray_lift_error"),
    ),
    DownloadSpec(
        filename="low_key_hard_days_night_hotel_guest_room.jpg",
        commons_file_name="Hard Days Night Hotel, a guest room, Liverpool 2009.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Hard_Days_Night_Hotel,_a_guest_room,_Liverpool_2009.jpg",
        notes="Dim hotel-room interior with warm lights and structured midtone objects.",
        expected_bucket="low_key",
        expected_failure_modes=("shadow_crush", "middle_gray_lift_error"),
    ),
    DownloadSpec(
        filename="low_key_hotel_room_in_nice.jpg",
        commons_file_name="Hotel room in Nice.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Hotel_room_in_Nice.jpg",
        notes="Dark hotel-room interior with bedding and furniture detail for low-key midtone retention checks.",
        expected_bucket="low_key",
        expected_failure_modes=("shadow_crush", "middle_gray_lift_error"),
    ),
    DownloadSpec(
        filename="low_key_seoul_garden_hotel_room.jpg",
        commons_file_name="SK Korea tour 首爾 最佳西方 首爾花園酒店 Best Western Premier Seoul Garden Hotel room interior curtain n furniture lighting July-2013.JPG",
        source_page="https://commons.wikimedia.org/wiki/File:SK_Korea_tour_%E9%A6%96%E7%88%BE_%E6%9C%80%E4%BD%B3%E8%A5%BF%E6%96%B9_%E9%A6%96%E7%88%BE%E8%8A%B1%E5%9C%92%E9%85%92%E5%BA%97_Best_Western_Premier_Seoul_Garden_Hotel_room_interior_curtain_n_furniture_lighting_July-2013.JPG",
        notes="Night hotel-room interior with curtains and warm practical lighting for structured low-key coverage.",
        expected_bucket="low_key",
        expected_failure_modes=("shadow_crush", "middle_gray_lift_error"),
    ),
    DownloadSpec(
        filename="text_ui_night_mecca_sign.jpg",
        commons_file_name="Street sign pointing to Masjid al-Haram with Abraj Al Bait Clock Tower at night, Mecca.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Street_sign_pointing_to_Masjid_al-Haram_with_Abraj_Al_Bait_Clock_Tower_at_night,_Mecca.jpg",
        notes="Night street sign with bright text edges on dark background, useful for halo and text clarity checks.",
        expected_bucket="text_ui",
        expected_failure_modes=("halo", "highlight_bloom"),
    ),
    DownloadSpec(
        filename="text_ui_boulevard_hotel_neon_sign.jpg",
        commons_file_name="Boulevard Hotel (Neon sign), Miami Beach.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Boulevard_Hotel_(Neon_sign),_Miami_Beach.jpg",
        notes="Neon hotel sign at night with strong bright text for text edge and halo checks.",
        expected_bucket="text_ui",
        expected_failure_modes=("halo", "highlight_bloom", "over_enhancement"),
    ),
    DownloadSpec(
        filename="text_ui_magnolia_cafe_neon_sign.jpg",
        commons_file_name="Magnolia Cafe neon sign at night.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Magnolia_Cafe_neon_sign_at_night.jpg",
        notes="Single neon cafe sign at night for text-edge, halo, and highlight bloom checks.",
        expected_bucket="text_ui",
        expected_failure_modes=("halo", "highlight_bloom", "over_enhancement"),
    ),
    DownloadSpec(
        filename="text_ui_shinjuku_colorful_neon_street_signs.jpg",
        commons_file_name="Colorful neon street signs in Kabukichō, Shinjuku, Tokyo.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Colorful_neon_street_signs_in_Kabukich%C5%8D,_Shinjuku,_Tokyo.jpg",
        notes="Dense colorful neon street signs for small-text visibility and local halo checks.",
        expected_bucket="text_ui",
        expected_failure_modes=("halo", "highlight_bloom", "over_enhancement"),
    ),
    DownloadSpec(
        filename="text_ui_iit_kharagpur_signboard_glowing_at_night.jpg",
        commons_file_name="IIT Kharagpur signboard glowing at night.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:IIT_Kharagpur_signboard_glowing_at_night.jpg",
        notes="Single bright glowing signboard for text-edge and bloom regression checks.",
        expected_bucket="text_ui",
        expected_failure_modes=("halo", "highlight_bloom", "over_enhancement"),
    ),
    DownloadSpec(
        filename="text_ui_dotonbori_osaka_night.jpg",
        commons_file_name="Dotonbori, Osaka, at night, November 2016.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Dotonbori,_Osaka,_at_night,_November_2016.jpg",
        notes="Dense night signage scene with many small bright text elements.",
        expected_bucket="text_ui",
        expected_failure_modes=("halo", "highlight_bloom", "over_enhancement"),
    ),
    DownloadSpec(
        filename="text_ui_talad_neon_night_market_signage.jpg",
        commons_file_name="Talad Neon Night Market Signage, Dec 2017.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Talad_Neon_Night_Market_Signage,_Dec_2017.jpg",
        notes="Backup dense neon signage scene for small-text and highlight bloom checks.",
        expected_bucket="text_ui",
        expected_failure_modes=("halo", "highlight_bloom", "over_enhancement"),
    ),
    DownloadSpec(
        filename="faces_skin_closeup_blonde_girl.jpg",
        commons_file_name="Closeup of a young blonde girl face looking up.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Closeup_of_a_young_blonde_girl_face_looking_up.jpg",
        notes="Close-up face photo for skin-tone and RGB relation checks.",
        expected_bucket="faces_skin",
        expected_failure_modes=("color_shift", "over_enhancement"),
    ),
    DownloadSpec(
        filename="faces_skin_boy_face_from_venezuela.jpg",
        commons_file_name="Boy Face from Venezuela.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Boy_Face_from_Venezuela.jpg",
        notes="Natural face portrait with different skin tone and outdoor light for skin-tone robustness checks.",
        expected_bucket="faces_skin",
        expected_failure_modes=("color_shift", "over_enhancement"),
    ),
    DownloadSpec(
        filename="faces_skin_full_body_african_woman_dancer.jpg",
        commons_file_name="NW Folklife 2008 - dancer and drummers 02.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:NW_Folklife_2008_-_dancer_and_drummers_02.jpg",
        notes="Full-body dark-skin subject in colorful clothing for RGB relation and whole-body skin rendering checks.",
        expected_bucket="faces_skin",
        expected_failure_modes=("color_shift", "over_enhancement"),
    ),
    DownloadSpec(
        filename="faces_skin_india_delhi_portrait_of_a_man.jpg",
        commons_file_name="India - Delhi portrait of a man - 4780.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:India_-_Delhi_portrait_of_a_man_-_4780.jpg",
        notes="Natural male portrait under daylight for skin-tone robustness and mid-tone handling checks.",
        expected_bucket="faces_skin",
        expected_failure_modes=("color_shift", "over_enhancement"),
    ),
    DownloadSpec(
        filename="faces_skin_fietta_jarque.jpg",
        commons_file_name="Fietta Jarque.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Fietta_Jarque.jpg",
        notes="Color head-and-shoulders portrait for skin-tone stability and RGB drift checks.",
        expected_bucket="faces_skin",
        expected_failure_modes=("color_shift", "over_enhancement"),
    ),
    DownloadSpec(
        filename="faces_skin_zukhra.jpg",
        commons_file_name="Zukhra.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Zukhra.jpg",
        notes="Color portrait with natural facial tones for skin rendering robustness checks.",
        expected_bucket="faces_skin",
        expected_failure_modes=("color_shift", "over_enhancement"),
    ),
    DownloadSpec(
        filename="low_light_noisy_room_load_shedding_west_bengal.jpg",
        commons_file_name="A room during load shedding at night in West Bengal, India.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:A_room_during_load_shedding_at_night_in_West_Bengal,_India.jpg",
        notes="Very dark room under low light with smartphone-like noise risk and small light sources.",
        expected_bucket="low_light_noisy",
        expected_failure_modes=("noise_boost", "shadow_crush", "middle_gray_lift_error"),
    ),
    DownloadSpec(
        filename="low_light_noisy_control_room_at_night.jpg",
        commons_file_name="Control room at night - Cb-cr-night-pano4.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Control_room_at_night_-_Cb-cr-night-pano4.jpg",
        notes="Night control room with dark noisy regions and monitor highlights for low-light-noisy coverage.",
        expected_bucket="low_light_noisy",
        expected_failure_modes=("noise_boost", "shadow_crush", "highlight_bloom"),
    ),
    DownloadSpec(
        filename="low_light_noisy_my_room_for_the_night.jpg",
        commons_file_name="My room for the night - geograph.org.uk - 5345014.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:My_room_for_the_night_-_geograph.org.uk_-_5345014.jpg",
        notes="Low-light room with coarse textures and limited light, useful for noise amplification checks.",
        expected_bucket="low_light_noisy",
        expected_failure_modes=("noise_boost", "shadow_crush", "middle_gray_lift_error"),
    ),
    DownloadSpec(
        filename="low_light_noisy_a_room_for_the_night.jpg",
        commons_file_name="A room for the night - geograph.org.uk - 4761216.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:A_room_for_the_night_-_geograph.org.uk_-_4761216.jpg",
        notes="Low-light room scene with dark surfaces and small local lights for noisy-low-light coverage.",
        expected_bucket="low_light_noisy",
        expected_failure_modes=("noise_boost", "shadow_crush", "middle_gray_lift_error"),
    ),
    DownloadSpec(
        filename="low_light_noisy_belmont_ferry_waiting_room_night.jpg",
        commons_file_name="Waiting room at Belmont ferry terminal at night - geograph.org.uk - 2626996.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Waiting_room_at_Belmont_ferry_terminal_at_night_-_geograph.org.uk_-_2626996.jpg",
        notes="Low-light waiting room with small bright fixtures and dark coarse regions for noisy-night behavior.",
        expected_bucket="low_light_noisy",
        expected_failure_modes=("noise_boost", "shadow_crush", "highlight_bloom"),
    ),
    DownloadSpec(
        filename="low_light_noisy_room_for_the_night_geograph.jpg",
        commons_file_name="Room for the night^ - geograph.org.uk - 56226.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Room_for_the_night%5E_-_geograph.org.uk_-_56226.jpg",
        notes="Backup low-light room sample with dim structure for dark-noise amplification checks.",
        expected_bucket="low_light_noisy",
        expected_failure_modes=("noise_boost", "shadow_crush", "middle_gray_lift_error"),
    ),
    DownloadSpec(
        filename="gradient_sky_at_dusk_towards_sunset.jpg",
        commons_file_name="Sky gradient at dusk towards sunset.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Sky_gradient_at_dusk_towards_sunset.jpg",
        notes="Smooth sky gradient for banding and contour checks.",
        expected_bucket="gradient",
        expected_failure_modes=("banding",),
    ),
    DownloadSpec(
        filename="gradient_sky_gradient_pd.jpg",
        commons_file_name="Sky gradient.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Sky_gradient.jpg",
        notes="Public-domain smooth sky gradient for additional banding and contour checks.",
        expected_bucket="gradient",
        expected_failure_modes=("banding",),
    ),
    DownloadSpec(
        filename="gradient_blue_to_yellow_sky.jpg",
        commons_file_name="Blue-to-yellow gradient sky.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Blue-to-yellow_gradient_sky.jpg",
        notes="Simple blue-to-yellow sky ramp for banding and tone smoothness checks.",
        expected_bucket="gradient",
        expected_failure_modes=("banding",),
    ),
    DownloadSpec(
        filename="gradient_dark_to_light_blue_sky.jpg",
        commons_file_name="Dark to light blue sky.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Dark_to_light_blue_sky.jpg",
        notes="Smooth dark-to-light blue sky gradient for shadow-side banding checks.",
        expected_bucket="gradient",
        expected_failure_modes=("banding",),
    ),
    DownloadSpec(
        filename="high_contrast_tree_silhouette_sunset.jpg",
        commons_file_name="Silhouette of a tree during sunset.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Silhouette_of_a_tree_during_sunset.jpg",
        notes="High-contrast silhouette scene for halo and over-enhancement checks.",
        expected_bucket="high_contrast",
        expected_failure_modes=("halo", "over_enhancement"),
    ),
    DownloadSpec(
        filename="high_contrast_couple_silhouette_sunset.jpg",
        commons_file_name="A couple silhouette at Ras jebel beach during a golden sunset.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:A_couple_silhouette_at_Ras_jebel_beach_during_a_golden_sunset.jpg",
        notes="Strong silhouette against warm sunset for high-contrast edge and highlight behavior.",
        expected_bucket="high_contrast",
        expected_failure_modes=("halo", "over_enhancement"),
    ),
    DownloadSpec(
        filename="high_contrast_cactus_silhouettes_desert.jpg",
        commons_file_name="Cactus Silhouettes in desert.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Cactus_Silhouettes_in_desert.jpg",
        notes="Dark cactus silhouettes against bright sunset sky for hard-edge contrast behavior.",
        expected_bucket="high_contrast",
        expected_failure_modes=("halo", "over_enhancement"),
    ),
    DownloadSpec(
        filename="high_contrast_fisherman_pirogue_sunset_laos.jpg",
        commons_file_name="Silhouette of a fisherman standing on his pirogue at sunset with orange clouds in Don Det Si Phan Don Laos.jpg",
        source_page="https://commons.wikimedia.org/wiki/File:Silhouette_of_a_fisherman_standing_on_his_pirogue_at_sunset_with_orange_clouds_in_Don_Det_Si_Phan_Don_Laos.jpg",
        notes="Thin dark subject against bright sunset clouds for halo and hard-edge contrast checks.",
        expected_bucket="high_contrast",
        expected_failure_modes=("halo", "over_enhancement"),
    ),
)


def _build_download_url(commons_file_name: str, *, width: int) -> str:
    quoted = urllib.parse.quote(commons_file_name, safe="()!,")
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{quoted}?width={width}"


def _download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    user_agent = "ContrastTestImageFetcher/1.0 (+https://github.com/onions222/contrast_enhancement)"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
        destination.write_bytes(data)
        return
    except Exception as primary_exc:
        try:
            subprocess.run(
                [
                    "curl",
                    "-sS",
                    "-L",
                    "--fail",
                    "-A",
                    user_agent,
                    "-o",
                    str(destination),
                    url,
                ],
                check=True,
                timeout=60,
            )
            if not destination.exists() or destination.stat().st_size == 0:
                raise RuntimeError("curl fallback produced an empty file")
        except Exception:
            if destination.exists() and destination.stat().st_size == 0:
                destination.unlink()
            raise primary_exc


def _apply_curated_overrides(entries):
    spec_by_filename = {spec.filename: spec for spec in DOWNLOAD_SPECS}
    overridden = []
    for entry in entries:
        spec = spec_by_filename.get(entry.filename)
        if spec is None:
            overridden.append(entry)
            continue
        overridden.append(
            replace(
                entry,
                scene_tag=spec.expected_bucket,
                difficulty_tag=entry.difficulty_tag,
                expected_failure_modes="|".join(spec.expected_failure_modes),
                notes=spec.notes,
            )
        )
    return overridden


def main() -> dict[str, object]:
    RAW_ROOT.mkdir(parents=True, exist_ok=True)
    downloaded: list[dict[str, object]] = []
    failed: list[dict[str, object]] = []
    for spec in DOWNLOAD_SPECS:
        destination = RAW_ROOT / spec.filename
        download_url = _build_download_url(spec.commons_file_name, width=spec.width)
        if destination.exists() and destination.stat().st_size > 0:
            downloaded.append(
                {
                    "filename": spec.filename,
                    "download_url": download_url,
                    "source_page": spec.source_page,
                    "notes": spec.notes,
                    "expected_bucket": spec.expected_bucket,
                    "expected_failure_modes": list(spec.expected_failure_modes),
                    "status": "cached",
                }
            )
            print(f"Using cached {spec.filename}", flush=True)
            continue
        print(f"Downloading {spec.filename} ...", flush=True)
        try:
            _download_file(download_url, destination)
        except Exception as exc:
            failed.append(
                {
                    "filename": spec.filename,
                    "download_url": download_url,
                    "source_page": spec.source_page,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"Failed {spec.filename}: {type(exc).__name__}: {exc}", flush=True)
            continue
        downloaded.append(
            {
                "filename": spec.filename,
                "download_url": download_url,
                "source_page": spec.source_page,
                "notes": spec.notes,
                "expected_bucket": spec.expected_bucket,
                "expected_failure_modes": list(spec.expected_failure_modes),
                "status": "downloaded",
            }
        )
        print(f"Saved {spec.filename}", flush=True)

    CURATED_METADATA_PATH.write_text(json.dumps({"downloaded": downloaded, "failed": failed}, indent=2), encoding="utf-8")

    entries = build_manifest_entries(
        dataset_id="wikimedia_commons",
        source="Wikimedia Commons Curated Set",
        source_url="https://commons.wikimedia.org/",
        license_name="see-per-file-license-on-source-page",
        input_root=RAW_ROOT,
        split="test",
    )
    entries = _apply_curated_overrides(entries)
    export_manifest_csv(CURATED_MANIFEST_PATH, entries)
    public_subset_summary = build_public_eval_subset()
    summary = {
        "raw_root": str(RAW_ROOT),
        "manifest_path": str(CURATED_MANIFEST_PATH),
        "metadata_path": str(CURATED_METADATA_PATH),
        "downloaded_count": len(downloaded),
        "failed_count": len(failed),
        "downloaded_files": downloaded,
        "failed_files": failed,
        "public_subset_summary": public_subset_summary,
    }
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
