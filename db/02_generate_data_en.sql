-- =====================================================================
--  English variant of the demo dataset (~1,000,000 order lines) -- same structure and volumes
--  (250 000 commandes de 1 à 7 lignes, 5 000 clients, 144 commerciaux,
--   2 000 produits, 3 ans de dates). Reproductible (setseed).
-- =====================================================================
\timing on
SET synchronous_commit = off;
SELECT setseed(0.4242);

TRUNCATE staging.orders;

-- Villes (ville, département, région)
CREATE TEMP TABLE gen_city (id serial PRIMARY KEY, city text, dept text, region text);
INSERT INTO gen_city(city, dept, region) VALUES
('Loudéac','22','Bretagne'),('Saint-Brieuc','22','Bretagne'),('Lannion','22','Bretagne'),('Dinan','22','Bretagne'),('Guingamp','22','Bretagne'),
('Pontivy','56','Bretagne'),('Vannes','56','Bretagne'),('Lorient','56','Bretagne'),('Ploërmel','56','Bretagne'),('Quimper','29','Bretagne'),
('Brest','29','Bretagne'),('Morlaix','29','Bretagne'),('Carhaix-Plouguer','29','Bretagne'),('Rennes','35','Bretagne'),('Fougères','35','Bretagne'),
('Vitré','35','Bretagne'),('Redon','35','Bretagne'),('Nantes','44','Pays de la Loire'),('Châteaubriant','44','Pays de la Loire'),('Ancenis','44','Pays de la Loire'),
('Angers','49','Pays de la Loire'),('Cholet','49','Pays de la Loire'),('Saumur','49','Pays de la Loire'),('Laval','53','Pays de la Loire'),('Mayenne','53','Pays de la Loire'),
('Château-Gontier','53','Pays de la Loire'),('Le Mans','72','Pays de la Loire'),('La Flèche','72','Pays de la Loire'),('La Roche-sur-Yon','85','Pays de la Loire'),('Les Herbiers','85','Pays de la Loire'),
('Fontenay-le-Comte','85','Pays de la Loire'),('Niort','79','Nouvelle-Aquitaine'),('Parthenay','79','Nouvelle-Aquitaine'),('Bressuire','79','Nouvelle-Aquitaine'),('Poitiers','86','Nouvelle-Aquitaine'),
('Caen','14','Normandie'),('Bayeux','14','Normandie'),('Lisieux','14','Normandie'),('Saint-Lô','50','Normandie'),('Avranches','50','Normandie'),
('Coutances','50','Normandie'),('Alençon','61','Normandie'),('Flers','61','Normandie'),('Argentan','61','Normandie'),('Évreux','27','Normandie'),
('Rouen','76','Normandie'),('Amiens','80','Hauts-de-France'),('Arras','62','Hauts-de-France'),('Lille','59','Hauts-de-France'),('Saint-Quentin','02','Hauts-de-France'),
('Rodez','12','Occitanie'),('Aurillac','15','Auvergne-Rhône-Alpes'),('Clermont-Ferrand','63','Auvergne-Rhône-Alpes'),('Limoges','87','Nouvelle-Aquitaine'),('Tulle','19','Nouvelle-Aquitaine'),
('Bourges','18','Centre-Val de Loire'),('Châteauroux','36','Centre-Val de Loire'),('Tours','37','Centre-Val de Loire'),('Blois','41','Centre-Val de Loire'),('Orléans','45','Centre-Val de Loire'),
('Chartres','28','Centre-Val de Loire'),('Troyes','10','Grand Est'),('Dijon','21','Bourgogne-Franche-Comté'),('Mâcon','71','Bourgogne-Franche-Comté'),('Lons-le-Saunier','39','Bourgogne-Franche-Comté'),
('Besançon','25','Bourgogne-Franche-Comté'),('Épinal','88','Grand Est'),('Nancy','54','Grand Est'),('Metz','57','Grand Est'),('Strasbourg','67','Grand Est'),
('Colmar','68','Grand Est'),('Bourg-en-Bresse','01','Auvergne-Rhône-Alpes'),('Lyon','69','Auvergne-Rhône-Alpes'),('Grenoble','38','Auvergne-Rhône-Alpes'),('Chambéry','73','Auvergne-Rhône-Alpes'),
('Annecy','74','Auvergne-Rhône-Alpes'),('Valence','26','Auvergne-Rhône-Alpes'),('Toulouse','31','Occitanie'),('Auch','32','Occitanie'),('Tarbes','65','Occitanie'),
('Pau','64','Nouvelle-Aquitaine'),('Mont-de-Marsan','40','Nouvelle-Aquitaine'),('Agen','47','Nouvelle-Aquitaine'),('Périgueux','24','Nouvelle-Aquitaine'),('Bordeaux','33','Nouvelle-Aquitaine'),
('Angoulême','16','Nouvelle-Aquitaine'),('La Rochelle','17','Nouvelle-Aquitaine'),('Cahors','46','Occitanie'),('Montauban','82','Occitanie'),('Albi','81','Occitanie'),
('Carcassonne','11','Occitanie'),('Perpignan','66','Occitanie'),('Montpellier','34','Occitanie'),('Nîmes','30','Occitanie'),('Avignon','84','Provence-Alpes-Côte d Azur'),
('Marseille','13','Provence-Alpes-Côte d Azur'),('Gap','05','Provence-Alpes-Côte d Azur'),('Digne-les-Bains','04','Provence-Alpes-Côte d Azur'),('Nice','06','Provence-Alpes-Côte d Azur'),('Melun','77','Île-de-France');

-- Clients : 5 000 exploitations
CREATE TEMP TABLE gen_customer AS
WITH base AS (
    SELECT i,
           1 + floor(random()*100)::int AS city_id,
           floor(random()*10)::int  AS f_idx,
           floor(random()*50)::int  AS s_idx,
           floor(random()*20)::int  AS l_idx,
           floor(random()*9)::int   AS seg_idx,
           random()                 AS r
    FROM generate_series(1, 5000) i)
SELECT b.i AS id,
       'C' || lpad(b.i::text, 6, '0') AS code,
       (ARRAY['EARL','GAEC','SCEA','SARL','Farm','Estate','EARL','GAEC','SCEA','Farm'])[b.f_idx+1]
       || ' ' ||
       CASE WHEN b.r < 0.5
            THEN (ARRAY['Le Goff','Le Roux','Tanguy','Le Gall','Guillou','Morvan','Riou','Le Bras','Hamon','Jaouen','Martin','Bernard','Dubois','Thomas','Robert','Richard','Petit','Durand','Leroy','Moreau','Simon','Laurent','Lefebvre','Michel','Garcia','David','Bertrand','Roux','Vincent','Fournier','Morel','Girard','André','Mercier','Dupont','Lambert','Bonnet','François','Martinez','Legrand','Garnier','Faure','Rousseau','Blanc','Guérin','Muller','Henry','Roussel','Nicolas','Perrin'])[b.s_idx+1]
            ELSE (ARRAY['Kerguelen','Kerbiquet','La Ville Neuve','Les Landes','Le Bourg','La Croix','Kervran','Le Clos','Les Rouges Terres','La Grande Métairie','Kerlouan','Le Moulin','Beaulieu','La Haute Folie','Kerandraon','Le Pont Neuf','Les Fontaines','Kerdaniel','Le Verger','La Chesnaie'])[b.l_idx+1]
       END || ' - ' || c.city AS name,
       c.city, c.dept, c.region,
       (ARRAY['Dairy cattle farmer','Beef cattle farmer','Pig farmer','Poultry farmer','Arable farmer','Market gardener','Winegrower','Sheep and goat farmer','Private customer'])[b.seg_idx+1] AS segment
FROM base b JOIN gen_city c ON c.id = b.city_id;

-- Commerciaux : 12 par région
CREATE TEMP TABLE gen_rep AS
WITH reg AS (SELECT region, row_number() OVER (ORDER BY region) AS region_idx FROM (SELECT DISTINCT region FROM gen_city) x),
     base AS (SELECT r.region, r.region_idx, k, floor(random()*24)::int AS fn_idx, floor(random()*50)::int AS s_idx
              FROM reg r CROSS JOIN generate_series(1, 12) k)
SELECT row_number() OVER (ORDER BY region_idx, k) AS id,
       'REP' || lpad((row_number() OVER (ORDER BY region_idx, k))::text, 3, '0') AS code,
       (ARRAY['Yann','Morgane','Erwan','Anne','Gwenaël','Solenn','Loïc','Nolwenn','Thomas','Julie','Pierre','Marie','Nicolas','Sophie','Julien','Camille','Maxime','Léa','Antoine','Chloé','Alexandre','Manon','Vincent','Élodie'])[fn_idx+1]
       || ' ' ||
       (ARRAY['Le Goff','Le Roux','Tanguy','Le Gall','Guillou','Morvan','Riou','Le Bras','Hamon','Jaouen','Martin','Bernard','Dubois','Thomas','Robert','Richard','Petit','Durand','Leroy','Moreau','Simon','Laurent','Lefebvre','Michel','Garcia','David','Bertrand','Roux','Vincent','Fournier','Morel','Girard','André','Mercier','Dupont','Lambert','Bonnet','François','Martinez','Legrand','Garnier','Faure','Rousseau','Blanc','Guérin','Muller','Henry','Roussel','Nicolas','Perrin'])[s_idx+1] AS name,
       region, k
FROM base;

-- Catégories de produits (fournitures agricoles) avec noms de base et fourchettes de prix
CREATE TEMP TABLE gen_cat (id serial PRIMARY KEY, category text, names text[], pmin numeric, pmax numeric);
INSERT INTO gen_cat(category, names, pmin, pmax) VALUES
('Animal feed',               ARRAY['Dairy cow feed 25 kg','Calf feed 25 kg','Pig grower pellets 25 kg','Layer hen feed 20 kg','Poultry mash 25 kg','Alfalfa hay 300 kg','Mineral lick block 10 kg','Sheep concentrate 25 kg'], 8, 60),
('Animal hygiene and health', ARRAY['Barn disinfectant 20 L','Cattle dewormer 1 L','Teat dip 20 L','Mineral supplement 25 kg','Hoof spray 500 mL','Teat wipes x1000','Barn insecticide 5 L'], 15, 180),
('Livestock and buildings',   ARRAY['Constant-level water trough','Galvanized hay rack','6-place feed barrier','Rubber cubicle mat','Galvanized gate 4 m','Piglet feeder','Infrared heat lamp 250 W','Barn fan 50 cm'], 30, 1500),
('Fencing',                   ARRAY['Fence energizer 12 V','Fiberglass posts x50','Fence wire 400 m','Ring insulators x100','Electric gate handle','Fence tape 200 m','Battery 12 V 100 Ah'], 5, 400),
('Seeds and crops',           ARRAY['Maize seed 50,000 kernels','Perennial ryegrass 25 kg','Red clover 10 kg','Wheat seed 25 kg','NPK fertilizer 15-15-15 50 kg','Silage sheet 12 x 50 m','Round bale net 3000 m','Bale wrap film 750 mm'], 20, 350),
('Equipment and tools',       ARRAY['Backpack sprayer 16 L','Petrol chainsaw 45 cm','Brushcutter 42 cc','Pressure washer 150 bar','Petrol water pump','Generator 5 kVA','Wheelbarrow 100 L','Compressor 50 L'], 40, 2500),
('Workwear and PPE',          ARRAY['Farm boots','Work overalls','Milking gloves x100','Rain jacket','Multi-pocket trousers','Safety shoes S3','Bib overalls'], 5, 120),
('Garden and green spaces',   ARRAY['Petrol lawnmower 51 cm','Potting soil 70 L','Garden hose 50 m','Hard-wearing lawn seed 5 kg','Pro pruning shears','Tunnel greenhouse 6 m2','Electric hedge trimmer'], 8, 900);

-- Produits : 2 000 références
CREATE TEMP TABLE gen_product AS
WITH base AS (SELECT i, 1 + ((i-1) % 8) AS cat_id, random() AS r1, random() AS r2, random() AS r3, random() AS r4
              FROM generate_series(1, 2000) i)
SELECT b.i AS id,
       'P' || lpad(b.i::text, 6, '0') AS code,
       (ARRAY['','','Premium ','Eco ','Pro '])[1 + floor(b.r1*5)::int] || c.names[1 + floor(b.r2*array_length(c.names,1))::int] AS name,
       c.category,
       (ARRAY['Vital Concept','Bio Armor','AgriNova','Lacme','Gallagher','Stihl','Husqvarna','Kärcher','La Buvette','Suevia','Patura','Zoetis','Elanco','MSD','Novatech','Lallemand','KWS','Pioneer','Yara','Timac Agro','Aigle','Le Chameau','Delta Plus','Portwest'])[1 + floor(b.r3*24)::int] AS brand,
       round((c.pmin + b.r4*(c.pmax - c.pmin))::numeric, 2) AS price
FROM base b JOIN gen_cat c ON c.id = b.cat_id;

-- Commandes : 250 000 entêtes de 1 à 7 lignes sur 3 ans (2023-2025)
CREATE TEMP TABLE gen_order AS
SELECT o AS order_no,
       1 + floor(random()*5000)::int AS cust_id,
       date '2023-01-01' + floor(random()*1096)::int AS order_date,
       1 + floor(random()*7)::int AS n_lines
FROM generate_series(1, 250000) o;

-- Lignes de commandes → table source dénormalisée
INSERT INTO staging.orders (order_line_id, order_id, order_date,
        customer_code, customer_name, customer_city, customer_dept, customer_segment,
        salesrep_code, salesrep_name, salesrep_region,
        product_code, product_name, product_category, product_brand,
        quantity, unit_price)
SELECT row_number() OVER (ORDER BY l.order_no, l.line_no),
       'CMD' || lpad(l.order_no::text, 8, '0'),
       l.order_date,
       c.code, c.name, c.city, c.dept, c.segment,
       r.code, r.name, r.region,
       p.code, p.name, p.category, p.brand,
       l.quantity,
       round(p.price * (1 - l.discount), 2)
FROM (SELECT o.order_no, o.order_date, o.cust_id, ln AS line_no,
             1 + floor(random()*2000)::int AS prod_id,
             1 + floor(random()*random()*30)::int AS quantity,
             (ARRAY[0, 0, 0, 0.05, 0.10])[1 + floor(random()*5)::int] AS discount
      FROM gen_order o CROSS JOIN LATERAL generate_series(1, o.n_lines) ln) l
JOIN gen_customer c ON c.id = l.cust_id
JOIN gen_rep      r ON r.region = c.region AND r.k = 1 + (c.id % 12)
JOIN gen_product  p ON p.id = l.prod_id;

ANALYZE staging.orders;

SELECT count(*) AS lignes, count(DISTINCT order_id) AS commandes, count(DISTINCT customer_code) AS clients,
       count(DISTINCT salesrep_code) AS commerciaux, count(DISTINCT product_code) AS produits,
       count(DISTINCT order_date) AS jours, min(order_date), max(order_date),
       pg_size_pretty(pg_total_relation_size('staging.orders')) AS taille
FROM staging.orders;
