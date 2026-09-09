-- =====================================================================
--  French variant of the demo data set (~1,000,000 order lines): same structure and volumes
--  as 02_generate_data.sql, with French labels for segments, categories and products
--  (250,000 orders of 1 to 7 lines, 5,000 customers, 144 sales reps, 2,000 products,
--   3 years of dates). Reproducible (setseed).
-- =====================================================================
\timing on
SET synchronous_commit = off;
SELECT setseed(0.4242);

TRUNCATE staging.orders;

-- Cities (city, department, region)
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

-- Customers: 5,000 farms
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
       (ARRAY['EARL','GAEC','SCEA','SARL','Ferme','Domaine','EARL de','GAEC de','SCEA du','Ferme de'])[b.f_idx+1]
       || ' ' ||
       CASE WHEN b.r < 0.5
            THEN (ARRAY['Le Goff','Le Roux','Tanguy','Le Gall','Guillou','Morvan','Riou','Le Bras','Hamon','Jaouen','Martin','Bernard','Dubois','Thomas','Robert','Richard','Petit','Durand','Leroy','Moreau','Simon','Laurent','Lefebvre','Michel','Garcia','David','Bertrand','Roux','Vincent','Fournier','Morel','Girard','André','Mercier','Dupont','Lambert','Bonnet','François','Martinez','Legrand','Garnier','Faure','Rousseau','Blanc','Guérin','Muller','Henry','Roussel','Nicolas','Perrin'])[b.s_idx+1]
            ELSE (ARRAY['Kerguelen','Kerbiquet','La Ville Neuve','Les Landes','Le Bourg','La Croix','Kervran','Le Clos','Les Rouges Terres','La Grande Métairie','Kerlouan','Le Moulin','Beaulieu','La Haute Folie','Kerandraon','Le Pont Neuf','Les Fontaines','Kerdaniel','Le Verger','La Chesnaie'])[b.l_idx+1]
       END || ' - ' || c.city AS name,
       c.city, c.dept, c.region,
       (ARRAY['Éleveur bovin lait','Éleveur bovin viande','Éleveur porcin','Aviculteur','Grandes cultures','Maraîcher','Viticulteur','Éleveur ovin-caprin','Particulier'])[b.seg_idx+1] AS segment
FROM base b JOIN gen_city c ON c.id = b.city_id;

-- Sales reps: 12 per region
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

-- Product categories (farm supplies) with base names and price ranges
CREATE TEMP TABLE gen_cat (id serial PRIMARY KEY, category text, names text[], pmin numeric, pmax numeric);
INSERT INTO gen_cat(category, names, pmin, pmax) VALUES
('Alimentation animale',    ARRAY['Aliment vaches laitières 25 kg','Aliment veaux 25 kg','Granulés porcs croissance 25 kg','Aliment poules pondeuses 20 kg','Mash volailles 25 kg','Foin de luzerne 300 kg','Bloc à lécher 10 kg','Concentré ovins 25 kg'], 8, 60),
('Hygiène et santé animale', ARRAY['Désinfectant bâtiment 20 L','Vermifuge bovins 1 L','Produit de trempage trayons 20 L','Complément minéral 25 kg','Spray onglons 500 mL','Lingettes de trayon x1000','Insecticide bâtiment 5 L'], 15, 180),
('Élevage et bâtiment',      ARRAY['Abreuvoir à niveau constant','Râtelier galvanisé','Cornadis 6 places','Tapis logette caoutchouc','Barrière galvanisée 4 m','Nourrisseur porcelets','Lampe chauffante IR 250 W','Ventilateur bâtiment 50 cm'], 30, 1500),
('Clôture',                  ARRAY['Électrificateur 12 V','Piquet fibre de verre x50','Fil de clôture 400 m','Isolateur annulaire x100','Poignée de porte électrique','Ruban de clôture 200 m','Batterie 12 V 100 Ah'], 5, 400),
('Semences et cultures',     ARRAY['Semence maïs 50 000 grains','Ray-grass anglais 25 kg','Trèfle violet 10 kg','Blé tendre semence 25 kg','Engrais NPK 15-15-15 50 kg','Bâche ensilage 12 x 50 m','Filet balles rondes 3000 m','Film enrubannage 750 mm'], 20, 350),
('Équipement et outillage',  ARRAY['Pulvérisateur à dos 16 L','Tronçonneuse thermique 45 cm','Débroussailleuse 42 cc','Nettoyeur haute pression 150 bar','Pompe à eau thermique','Groupe électrogène 5 kVA','Brouette 100 L','Compresseur 50 L'], 40, 2500),
('Vêtements et EPI',         ARRAY['Bottes agricoles','Combinaison de travail','Gants de traite x100','Veste de pluie','Pantalon multipoches','Chaussures de sécurité S3','Cotte à bretelles'], 5, 120),
('Jardin et espaces verts',  ARRAY['Tondeuse thermique 51 cm','Terreau universel 70 L','Tuyau arrosage 50 m','Gazon rustique 5 kg','Sécateur pro','Serre tunnel 6 m2','Taille-haie électrique'], 8, 900);

-- Products: 2,000 references
CREATE TEMP TABLE gen_product AS
WITH base AS (SELECT i, 1 + ((i-1) % 8) AS cat_id, random() AS r1, random() AS r2, random() AS r3, random() AS r4
              FROM generate_series(1, 2000) i)
SELECT b.i AS id,
       'P' || lpad(b.i::text, 6, '0') AS code,
       (ARRAY['','','Premium ','Éco ','Pro '])[1 + floor(b.r1*5)::int] || c.names[1 + floor(b.r2*array_length(c.names,1))::int] AS name,
       c.category,
       (ARRAY['Vital Concept','Bio Armor','AgriNova','Lacme','Gallagher','Stihl','Husqvarna','Kärcher','La Buvette','Suevia','Patura','Zoetis','Elanco','MSD','Novatech','Lallemand','KWS','Pioneer','Yara','Timac Agro','Aigle','Le Chameau','Delta Plus','Portwest'])[1 + floor(b.r3*24)::int] AS brand,
       round((c.pmin + b.r4*(c.pmax - c.pmin))::numeric, 2) AS price
FROM base b JOIN gen_cat c ON c.id = b.cat_id;

-- Orders: 250,000 headers of 1 to 7 lines over 3 years (2023-2025)
CREATE TEMP TABLE gen_order AS
SELECT o AS order_no,
       1 + floor(random()*5000)::int AS cust_id,
       date '2023-01-01' + floor(random()*1096)::int AS order_date,
       1 + floor(random()*7)::int AS n_lines
FROM generate_series(1, 250000) o;

-- Order lines -> denormalized source table
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

SELECT count(*) AS rows, count(DISTINCT order_id) AS orders, count(DISTINCT customer_code) AS customers,
       count(DISTINCT salesrep_code) AS salesreps, count(DISTINCT product_code) AS products,
       count(DISTINCT order_date) AS days, min(order_date), max(order_date),
       pg_size_pretty(pg_total_relation_size('staging.orders')) AS size
FROM staging.orders;
