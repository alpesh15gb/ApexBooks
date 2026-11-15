"""Default vehicle makes and models for the optional Automobile module.

Shops that sell or fit parts need old and new vehicles, so this list leans broad: popular Indian-market cars,
two-wheelers, commercial vehicles and three-wheelers, including discontinued models still on the road.
It is only a starting point. Each company can add its own makes and models, and hide the ones it never sells for,
from Settings. Nothing here is a fitment database: item fitment stores the names the shop chose.
"""

VEHICLE_TYPES = {
    'car': 'Cars and SUVs',
    'two_wheeler': 'Two-wheelers',
    'commercial': 'Trucks, buses and light commercial',
    'three_wheeler': 'Three-wheelers',
}

CATALOG_VERSION = 1


def _make(name, vehicle_type, models):
    return {'make': name, 'type': vehicle_type, 'models': list(dict.fromkeys(models))}


CATALOG = [
    # ---- Cars and SUVs ----
    _make('Maruti Suzuki', 'car', [
        '800', 'Alto', 'Alto K10', 'A-Star', 'Baleno', 'Brezza', 'Celerio', 'Ciaz', 'Dzire', 'Eeco', 'Ertiga', 'Estilo',
        'Fronx', 'Grand Vitara', 'Gypsy', 'Ignis', 'Invicto', 'Jimny', 'Kizashi', 'Omni', 'Ritz', 'S-Cross', 'S-Presso',
        'Swift', 'SX4', 'Victoris', 'Vitara Brezza', 'Wagon R', 'XL6', 'Zen', 'Zen Estilo']),
    _make('Hyundai', 'car', [
        'Accent', 'Alcazar', 'Aura', 'Creta', 'Eon', 'Elantra', 'Exter', 'Getz', 'Grand i10', 'Grand i10 Nios', 'i10', 'i20',
        'i20 N Line', 'Ioniq 5', 'Kona Electric', 'Santa Fe', 'Santro', 'Santro Xing', 'Sonata', 'Tucson', 'Venue',
        'Venue N Line', 'Verna', 'Xcent']),
    _make('Tata Motors', 'car', [
        'Altroz', 'Aria', 'Bolt', 'Curvv', 'Harrier', 'Hexa', 'Indica', 'Indica Vista', 'Indigo', 'Indigo CS', 'Manza',
        'Nano', 'Nexon', 'Punch', 'Safari', 'Safari Storme', 'Sierra', 'Sumo', 'Tiago', 'Tigor', 'Zest', 'Harrier EV',
        'Nexon EV', 'Punch EV', 'Tiago EV', 'Tigor EV', 'Winger']),
    _make('Mahindra', 'car', [
        'Alturas G4', 'Bolero', 'Bolero Neo', 'BE 6', 'Marazzo', 'NuvoSport', 'Quanto', 'Scorpio', 'Scorpio Classic',
        'Scorpio-N', 'Thar', 'Thar Roxx', 'TUV300', 'TUV300 Plus', 'Verito', 'Verito Vibe', 'XEV 9e', 'XUV300', 'XUV400',
        'XUV500', 'XUV700', 'XUV 3XO', 'Xylo', 'Logan', 'Armada', 'Commander', 'Marshal', 'Voyager']),
    _make('Kia', 'car', ['Carens', 'Carens Clavis', 'Carnival', 'EV6', 'EV9', 'Seltos', 'Sonet', 'Syros']),
    _make('Toyota', 'car', [
        'Camry', 'Corolla', 'Corolla Altis', 'Etios', 'Etios Liva', 'Etios Cross', 'Fortuner', 'Glanza', 'Hilux',
        'Innova', 'Innova Crysta', 'Innova Hycross', 'Land Cruiser', 'Land Cruiser Prado', 'Platinum Etios', 'Qualis',
        'Rumion', 'Urban Cruiser', 'Urban Cruiser Hyryder', 'Urban Cruiser Taisor', 'Vellfire', 'Yaris']),
    _make('Honda Cars', 'car', [
        'Accord', 'Amaze', 'BR-V', 'Brio', 'City', 'City Hybrid', 'Civic', 'CR-V', 'Elevate', 'Jazz', 'Mobilio', 'WR-V']),
    _make('Renault', 'car', ['Captur', 'Duster', 'Fluence', 'Kiger', 'Kwid', 'Lodgy', 'Pulse', 'Scala', 'Triber']),
    _make('Nissan', 'car', ['Evalia', 'Kicks', 'Magnite', 'Micra', 'Micra Active', 'Sunny', 'Teana', 'Terrano', 'X-Trail']),
    _make('Datsun', 'car', ['GO', 'GO+', 'redi-GO']),
    _make('Volkswagen', 'car', [
        'Ameo', 'Beetle', 'Jetta', 'Passat', 'Polo', 'Taigun', 'Tiguan', 'T-Roc', 'Vento', 'Virtus']),
    _make('Skoda', 'car', [
        'Fabia', 'Kodiaq', 'Kushaq', 'Kylaq', 'Laura', 'Octavia', 'Rapid', 'Slavia', 'Superb', 'Yeti']),
    _make('MG', 'car', ['Astor', 'Comet EV', 'Cyberster', 'Gloster', 'Hector', 'Hector Plus', 'Windsor EV', 'ZS EV']),
    _make('Ford', 'car', [
        'Aspire', 'Classic', 'EcoSport', 'Endeavour', 'Fiesta', 'Figo', 'Freestyle', 'Fusion', 'Ikon', 'Mondeo']),
    _make('Chevrolet', 'car', [
        'Aveo', 'Aveo U-VA', 'Beat', 'Captiva', 'Cruze', 'Enjoy', 'Optra', 'Sail', 'Sail U-VA', 'Spark', 'Tavera', 'Trailblazer']),
    _make('Fiat', 'car', ['Avventura', 'Grande Punto', 'Linea', 'Palio', 'Petra', 'Punto', 'Punto Evo', 'Siena', 'Uno']),
    _make('Jeep', 'car', ['Avenger', 'Compass', 'Grand Cherokee', 'Meridian', 'Wrangler']),
    _make('Citroen', 'car', ['Aircross', 'Basalt', 'C3', 'C5 Aircross', 'eC3']),
    _make('Mitsubishi', 'car', ['Lancer', 'Montero', 'Outlander', 'Pajero', 'Pajero Sport', 'Cedia']),
    _make('Isuzu', 'car', ['D-Max V-Cross', 'D-Max Hi-Lander', 'MU-X', 'MU-7']),
    _make('Force Motors', 'car', ['Gurkha', 'One']),
    _make('Hindustan Motors', 'car', ['Ambassador', 'Contessa']),
    _make('Premier', 'car', ['Padmini', 'Sigma', 'Rio']),
    _make('BMW', 'car', [
        '1 Series', '2 Series', '3 Series', '3 Series Gran Limousine', '5 Series', '6 Series', '7 Series', 'i4', 'i5', 'i7',
        'iX', 'iX1', 'M2', 'M3', 'M4', 'M5', 'X1', 'X2', 'X3', 'X4', 'X5', 'X6', 'X7', 'Z4']),
    _make('Mercedes-Benz', 'car', [
        'A-Class', 'B-Class', 'C-Class', 'CLA', 'E-Class', 'EQA', 'EQB', 'EQE', 'EQS', 'G-Class', 'GLA', 'GLB', 'GLC',
        'GLE', 'GLS', 'M-Class', 'Maybach S-Class', 'S-Class', 'SL', 'V-Class']),
    _make('Audi', 'car', [
        'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'e-tron', 'Q2', 'Q3', 'Q5', 'Q7', 'Q8', 'Q8 e-tron', 'R8', 'RS5', 'TT']),
    _make('Volvo Cars', 'car', ['C40 Recharge', 'EX30', 'S60', 'S80', 'S90', 'XC40', 'XC60', 'XC90']),
    _make('Land Rover', 'car', [
        'Defender', 'Discovery', 'Discovery Sport', 'Freelander 2', 'Range Rover', 'Range Rover Evoque',
        'Range Rover Sport', 'Range Rover Velar']),
    _make('Jaguar', 'car', ['E-Pace', 'F-Pace', 'F-Type', 'I-Pace', 'XE', 'XF', 'XJ']),
    _make('Lexus', 'car', ['ES', 'LC', 'LM', 'LS', 'LX', 'NX', 'RX', 'UX']),
    _make('Mini', 'car', ['Clubman', 'Convertible', 'Cooper', 'Countryman', 'Cooper SE']),
    _make('Porsche', 'car', ['718', '911', 'Cayenne', 'Macan', 'Panamera', 'Taycan']),
    _make('BYD', 'car', ['Atto 3', 'eMAX 7', 'Sealion 7', 'Seal']),
    _make('Tesla', 'car', ['Model 3', 'Model Y']),
    _make('Maserati', 'car', ['Ghibli', 'GranTurismo', 'Levante', 'Quattroporte']),
    _make('Lamborghini', 'car', ['Huracan', 'Revuelto', 'Urus']),
    _make('Ferrari', 'car', ['296 GTB', '488', 'Roma', 'SF90']),
    _make('Rolls-Royce', 'car', ['Cullinan', 'Ghost', 'Phantom', 'Spectre']),
    _make('Bentley', 'car', ['Bentayga', 'Continental GT', 'Flying Spur']),
    _make('Aston Martin', 'car', ['DB11', 'DBX', 'Vantage']),

    # ---- Two-wheelers ----
    _make('Hero MotoCorp', 'two_wheeler', [
        'Achiever', 'Destini 125', 'Duet', 'Glamour', 'Glamour Xtec', 'Karizma', 'Karizma XMR', 'Maestro Edge', 'Passion',
        'Passion Pro', 'Passion Plus', 'Passion XPro', 'Pleasure', 'Pleasure Plus', 'Splendor', 'Splendor Plus',
        'Splendor Pro', 'Splendor iSmart', 'Super Splendor', 'HF Deluxe', 'HF Dawn', 'CD Deluxe', 'CD 100', 'Hunk',
        'Impulse', 'Ignitor', 'Xtreme', 'Xtreme 160R', 'Xtreme 200S', 'Xpulse 200', 'Xoom', 'Zoom', 'Mavrick 440',
        'Ambition', 'CBZ', 'Joy', 'Street Smart', 'Vida V1']),
    _make('Honda Two-Wheelers', 'two_wheeler', [
        'Activa', 'Activa 125', 'Activa i', 'Aviator', 'CB Hornet 160R', 'CB Shine', 'CB Shine SP', 'CB Unicorn',
        'CB Unicorn 160', 'CB200X', 'CB350', 'CB350RS', 'CBR 250R', 'CBR 650R', 'Dio', 'Dio 125', 'Dream Neo',
        'Dream Yuga', 'Eterno', 'H’ness CB350', 'Livo', 'NX200', 'Navi', 'SP 125', 'SP 160', 'Shine 100',
        'Shine 125', 'Stunner', 'Trigger', 'Unicorn', 'X-Blade', 'Africa Twin', 'Activa Electric', 'QC1']),
    _make('Bajaj Auto', 'two_wheeler', [
        'Avenger', 'Avenger Cruise 220', 'Avenger Street 160', 'Boxer', 'CT 100', 'CT 110', 'CT 125X', 'Chetak',
        'Discover 100', 'Discover 110', 'Discover 125', 'Discover 150', 'Dominar 250', 'Dominar 400', 'Freedom 125',
        'Platina 100', 'Platina 110', 'Platina 110 H-Gear', 'Pulsar 125', 'Pulsar 150', 'Pulsar 180', 'Pulsar 200 NS',
        'Pulsar 220 F', 'Pulsar N160', 'Pulsar N250', 'Pulsar NS160', 'Pulsar NS400Z', 'Pulsar RS200', 'Pulsar AS',
        'Pulsar P150', 'Pulsar F250', 'V15', 'V12', 'Wind 125', 'XCD', 'Kristal', 'Super', 'Bajaj Chetak 35 Series']),
    _make('TVS Motor', 'two_wheeler', [
        'Apache RR 310', 'Apache RTR 160', 'Apache RTR 160 4V', 'Apache RTR 180', 'Apache RTR 200 4V', 'Apache RTX 300',
        'Apache RTR 310', 'Centra', 'Flame', 'Fiero', 'iQube', 'Jive', 'Jupiter', 'Jupiter 125', 'Max 100', 'NTORQ 125',
        'Phoenix', 'Radeon', 'Raider 125', 'Scooty Pep+', 'Scooty Streak', 'Scooty Zest', 'Sport', 'Star City',
        'Star City+', 'Victor', 'Wego', 'XL 100', 'XL100 Heavy Duty', 'Zeppelin', 'Orbiter', 'Ronin']),
    _make('Royal Enfield', 'two_wheeler', [
        'Bear 650', 'Bullet 350', 'Bullet 500', 'Classic 350', 'Classic 500', 'Classic 650', 'Continental GT 535',
        'Continental GT 650', 'Electra', 'Flying Flea', 'Guerrilla 450', 'Himalayan', 'Himalayan 450', 'Hunter 350',
        'Interceptor 650', 'Meteor 350', 'Scram 411', 'Shotgun 650', 'Super Meteor 650', 'Thunderbird 350',
        'Thunderbird 500', 'Thunderbird 350X', 'Lightning']),
    _make('Yamaha', 'two_wheeler', [
        'Alpha', 'Aerox 155', 'Crux', 'Enticer', 'Fascino', 'Fazer', 'Fazer 25', 'FZ', 'FZ-S', 'FZ-S FI', 'FZ-X', 'FZ25',
        'FZS 25', 'Gladiator', 'Libero', 'MT-15', 'MT-03', 'R15', 'R15 V3', 'R15 V4', 'R15M', 'R3', 'Ray ZR',
        'Ray ZR 125', 'RX 100', 'RX 135', 'RXZ', 'SZ-R', 'SZ-RR', 'Saluto', 'Saluto RX', 'Ybr 125', 'XSR 155', 'YZF R1']),
    _make('Suzuki Motorcycle', 'two_wheeler', [
        'Access 125', 'Avenis 125', 'Burgman Street', 'Burgman Street EX', 'Gixxer', 'Gixxer SF', 'Gixxer 250',
        'Gixxer SF 250', 'GS150R', 'Hayate', 'Heat', 'Hayabusa', 'Intruder', 'Lets', 'Samurai', 'Slingshot', 'V-Strom SX',
        'Zeus', 'Swish 125']),
    _make('KTM', 'two_wheeler', [
        '125 Duke', '200 Duke', '250 Duke', '390 Duke', '390 Adventure', '250 Adventure', '390 Adventure X', 'RC 125',
        'RC 200', 'RC 390', '490 Duke', '890 Duke']),
    _make('Husqvarna', 'two_wheeler', ['Svartpilen 250', 'Svartpilen 401', 'Vitpilen 250', 'Vitpilen 401']),
    _make('Kawasaki', 'two_wheeler', [
        'Eliminator', 'KLX 230', 'Ninja 300', 'Ninja 400', 'Ninja 500', 'Ninja 650', 'Ninja ZX-10R', 'Ninja ZX-6R', 'Versys 650',
        'Versys 1000', 'Vulcan S', 'W175', 'Z400', 'Z650', 'Z900']),
    _make('Triumph', 'two_wheeler', [
        'Bonneville', 'Scrambler 400 X', 'Speed 400', 'Speed Twin', 'Street Triple', 'Tiger 900', 'Tiger Sport 660', 'Trident 660']),
    _make('Harley-Davidson', 'two_wheeler', [
        'Fat Boy', 'Iron 883', 'Nightster', 'Pan America', 'Softail', 'Street 750', 'Sportster S', 'X440']),
    _make('Ducati', 'two_wheeler', ['Diavel', 'Monster', 'Multistrada', 'Panigale', 'Scrambler', 'Streetfighter', 'Hypermotard']),
    _make('BMW Motorrad', 'two_wheeler', ['C 400 GT', 'F 850 GS', 'G 310 GS', 'G 310 R', 'G 310 RR', 'R 1250 GS', 'S 1000 RR']),
    _make('Jawa Yezdi', 'two_wheeler', ['42', '42 Bobber', 'Jawa', 'Jawa 350', 'Perak', 'Roadking', 'Scrambler', 'Adventure', 'Roadster']),
    _make('Benelli', 'two_wheeler', ['302R', 'Imperiale 400', 'Leoncino 500', 'TNT 600', 'TRK 502', 'TRK 502X']),
    _make('Aprilia', 'two_wheeler', ['RS 457', 'SR 125', 'SR 160', 'SXR 160', 'Tuono 457']),
    _make('Vespa', 'two_wheeler', ['Elegante', 'LX 125', 'S 125', 'SXL 150', 'VXL 150', 'Vespa Racing Sixties', 'Notte']),
    _make('Piaggio Two-Wheelers', 'two_wheeler', ['Liberty', 'Zip']),
    _make('Ola Electric', 'two_wheeler', ['Gig', 'Roadster X', 'S1 Air', 'S1 Pro', 'S1 X']),
    _make('Ather Energy', 'two_wheeler', ['450 Apex', '450S', '450X', 'Rizta']),
    _make('Revolt', 'two_wheeler', ['RV1', 'RV400', 'RV BlazeX']),
    _make('Okinawa', 'two_wheeler', ['Praise Pro', 'R30', 'Ridge', 'iPraise']),
    _make('Hero Electric', 'two_wheeler', ['Atria', 'Flash', 'Nyx', 'Optima', 'Photon']),
    _make('Mahindra Two-Wheelers', 'two_wheeler', ['Centuro', 'Duro', 'Flyte', 'Gusto', 'Kine', 'Mojo', 'Pantero', 'Rodeo', 'Stallio']),
    _make('LML', 'two_wheeler', ['Freedom', 'NV', 'Select', 'Star', 'Vespa']),
    _make('Kinetic', 'two_wheeler', ['Blaze', 'Flyte', 'Honda', 'Luna', 'Luna Magnum', 'Nova', 'Safari', 'Zing', 'Zoom']),
    _make('Simple Energy', 'two_wheeler', ['One', 'Dot One']),
    _make('Kabira Mobility', 'two_wheeler', ['KM 3000', 'KM 4000', 'Hermes 75']),
    _make('Oben Electric', 'two_wheeler', ['Rorr']),
    _make('Ultraviolette', 'two_wheeler', ['F77']),

    # ---- Trucks, buses and light commercial ----
    _make('Tata Commercial', 'commercial', [
        '407', '709', '909', '1109', '1210', '1512', '1618', '2518', '2823', '3118', '3521', '4018', 'Ace', 'Ace Gold',
        'Ace EV', 'Ace Mega', 'Intra V10', 'Intra V30', 'Intra V50', 'Magic', 'Magic Iris', 'Prima', 'Signa', 'Starbus',
        'Ultra', 'Winger', 'Xenon', 'Yodha', 'LPT 1613', 'LPT 2518', 'LPT 3118', 'LPO 1618', 'LP 407', 'SFC 407',
        'Cityride', 'Marcopolo']),
    _make('Ashok Leyland', 'commercial', [
        'AVTR', 'Bada Dost', 'Boss', 'Captain', 'Comet', 'Dost', 'Dost Strong', 'Ecomet', 'Falcon', 'Guru', 'Jan Bus',
        'Lynx', 'Oyster', 'Partner', 'Saathi', 'Stile', 'Stallion', 'Tusker', 'Viking', 'U-Truck', 'Mitr']),
    _make('Eicher', 'commercial', [
        'Pro 1049', 'Pro 1059', 'Pro 2049', 'Pro 2059', 'Pro 2095', 'Pro 3008', 'Pro 3012', 'Pro 3015', 'Pro 3019',
        'Pro 5016', 'Pro 6016', 'Pro 6019', 'Pro 6028', 'Pro 6031', 'Pro 8031', 'Pro 8035', 'Pro 8049', 'Pro 8055',
        'Skyline Pro', 'Starline', 'Terra 16', 'Terra 25', 'Eicher 10.90', 'Eicher 11.10']),
    _make('Mahindra Commercial', 'commercial', [
        'Blazo X', 'Bolero Maxx Pik-Up', 'Bolero Pik-Up', 'Bolero Camper', 'Cruzio', 'Furio', 'Furio 7', 'Furio 11', 'Furio 14',
        'Jayo', 'Jeeto', 'Jeeto Plus', 'Loadking', 'Optimo', 'Supro', 'Supro Maxitruck', 'Imperio', 'Veero', 'Zeo', 'Truxo',
        'Tourister', 'Scorpio Pik-Up', 'Maxximo', 'Bolero Pick-Up City']),
    _make('BharatBenz', 'commercial', [
        '1015R', '1215R', '1217C', '1417R', '1617R', '1923C', '2823C', '3123R', '3528C', '4228R', '4828R', '5528T', '55280T',
        'MDT', 'HDT', 'School Bus', 'Staff Bus']),
    _make('Volvo Trucks and Buses', 'commercial', ['9400', '9600', 'FH', 'FM', 'FMX']),
    _make('SML Isuzu', 'commercial', ['Cargo', 'Executive', 'Prestige', 'Samrat', 'Sartaj']),
    _make('Force Commercial', 'commercial', ['Shaktiman', 'Traveller', 'Traveller 3350', 'Traveller 3700', 'Traveller 4020', 'Trax', 'Urbania']),
    _make('Swaraj Mazda', 'commercial', ['T3500', 'T3600', 'Bus']),
    _make('Maruti Suzuki Commercial', 'commercial', ['Eeco Cargo', 'Super Carry']),
    _make('Scania', 'commercial', ['P 360', 'G 410', 'R 450', 'Metrolink']),
    _make('Olectra', 'commercial', ['eBuzz K7', 'eBuzz K9']),

    # ---- Three-wheelers (and light cargo carriers) ----
    _make('Bajaj Three-Wheelers', 'three_wheeler', [
        'Compact', 'Compact RE', 'GoGo', 'Maxima C', 'Maxima Cargo', 'Maxima Z', 'Maxima XL Cargo', 'RE', 'RE 4S',
        'RE Optima', 'RE Compact 4S', 'Qute', 'Auto Rickshaw']),
    _make('Piaggio Ape', 'three_wheeler', [
        'Ape Auto', 'Ape City', 'Ape Extra', 'Ape Xtra LDX', 'Ape Xtra', 'Ape E-City', 'Ape E-Xtra FX', 'Ape Mini', 'Ape Truk']),
    _make('Mahindra Three-Wheelers', 'three_wheeler', ['Alfa', 'Alfa Load', 'Alfa Plus', 'Treo', 'Treo Zor', 'E-Alfa Mini', 'Zor Grand']),
    _make('TVS Three-Wheelers', 'three_wheeler', ['King', 'King Deluxe', 'King Duramax', 'King EV Max', 'King Kargo HD EV']),
    _make('Atul Auto', 'three_wheeler', ['Atul Gem', 'Atul Shakti', 'Atul Smart', 'Atul Elite Plus', 'Atul Gemini']),
    _make('Euler Motors', 'three_wheeler', ['HiLoad', 'Storm EV']),
    _make('Montra Electric', 'three_wheeler', ['Super Cargo', 'Eviator']),
    _make('Force Three-Wheelers', 'three_wheeler', ['Minidor', 'Fuji']),
    _make('Lohia Auto', 'three_wheeler', ['Humrahi', 'Narain', 'Comfort F2F']),
    _make('Kinetic Green', 'three_wheeler', ['Safar', 'Safar Jumbo', 'Safar Shakti']),
]

for _entry in CATALOG:
    _entry['models'] = sorted(_entry['models'], key=str.casefold)
CATALOG.sort(key=lambda entry: (list(VEHICLE_TYPES).index(entry['type']), entry['make'].casefold()))
