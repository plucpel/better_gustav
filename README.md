# 🏥 Gustav - Calculateur de Tubes de Prélèvement Sanguin (CHU de Québec)

Application locale haute performance permettant de sélectionner des analyses biologiques en langage naturel / sélection déterministe et de générer instantanément le nombre exact, les types, les couleurs de bouchons et l'ordre de prélèvement (**CLSI Standard Order of Draw**) des tubes requis, basée sur les données officielles du **Manuel des prélèvements du CHU de Québec (Gustav)**.

---

## ✨ Fonctionnalités

1. **Sélecteur Déterministe d'Analyses** :
   - Recherche instantanée avec auto-complétion, tolérance aux fautes de frappe et navigation clavier.
   - Reconnaissance automatique des acronymes médicaux français (`FSC`, `iono`, `créat`, `tropo`, `INR / Quick`, `PTT / TCA`, `TSH`, `gaz`, `fer`, etc.).
   - Raccourcis pour l'ajout en 1 clic de **Panels Cliniques** (*Bilan de base, Bilan hépatique, Bilan cardiaque, Bilan de coagulation, Sepsis, Bilan martial, etc.*).
2. **Moteur de Consolidation & Groupement de Tubes** :
   - Regroupe intelligemment les analyses compatibles partageant le même tube (ex: ~10 analyses de biochimie de routine regroupées dans **1 seul tube Menthe / Héparine-Lithium** ou **Doré / Gel**).
   - Sépare automatiquement les analyses nécessitant un tube dédié (`Lavande / EDTA`, `Bleu pâle / Citrate`, `Rose / Banque de sang`, `Gris / Fluorure`, `Seringues à gaz`).
3. **Ordre de Prélèvement Standardisé (CLSI H3-A6)** :
   - Affiche les tubes dans l'ordre chronologique exact de ponction veineuse pour éviter toute contamination d'additifs (*Hémocultures $\rightarrow$ Citrate $\rightarrow$ Sérum $\rightarrow$ Héparine $\rightarrow$ EDTA $\rightarrow$ Fluorure*).
4. **Adaptation par Site Hospitalier & Pédiatrie** :
   - Sélecteur de site hospitalier (*Hôpital Enfant-Jésus, HSFA, L'Hôtel-Dieu de Québec, CHUL, HSS, IUCPQ, Portneuf*).
   - Mode bascule **Adulte $\leftrightarrow$ Pédiatrique** (avec microtubes et volumes adaptés).
5. **Alertes Cliniques Spécifiques** :
   - Directives automatiques pour les analyses nécessitant d'être **à jeun**, **sur glace**, **à l'abri de la lumière** ou avec un **délai d'acheminement critique**.
6. **Lien Direct vers les Fiches Officielles Gustav** :
   - Visualisation détaillée et lien direct vers chaque fiche officielle du CHU de Québec.

---

## 🚀 Démarrage Rapide

### Option A : Sur Windows (Version Portable Clé en Main • 0 Installation Requise)
Un package autonome pour Windows a été créé dans le dossier `dist/` :
1. Téléchargez ou copiez le fichier **`dist/Gustav_Windows_Portable.zip`** (13.8 Mo).
2. Décompressez le fichier `.zip` sur n'importe quel PC Windows.
3. Double-cliquez sur **`Lancer_Gustav.bat`**.
*(Aucune installation de Python ou droits administrateur requis — un environnement Python Windows complet et toutes les dépendances sont déjà embarqués !)*

---

### Option B : Sur Mac / Linux (ou Windows avec Python existant)
Dans le dossier du projet :
```bash
pip install -r requirements.txt
python app.py
```
Ouvrez ensuite votre navigateur à l'adresse : **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 📦 Reconstruire le Package Windows Portable depuis Mac

Pour générer une nouvelle version du `.zip` autonome pour Windows depuis votre Mac :
```bash
python build_windows_portable.py
```
Le script téléchargera l'environnement embarqué Windows et emballera automatiquement le tout dans `dist/Gustav_Windows_Portable.zip`.

---

## 📁 Structure du Projet

```
Gustav/
├── app.py                      # Serveur FastAPI et points d'API REST
├── tube_calculator.py          # Moteur de calcul, groupement et tri selon l'ordre de prélèvement
├── medical_dictionary.py       # Dictionnaire des acronymes, synonymes et panels cliniques
├── gustav_crawler.py           # Script d'extraction et synchronisation du catalogue Gustav
├── data/
│   └── gustav_lab_catalog.json # Base locale de 1 605 fiches d'analyses biologiques
├── static/
│   └── index.html              # Interface web interactive responsive (Tailwind CSS)
└── test_api_endpoints.py       # Suite de tests automatisés de bout en bout
```

---

## 🔄 Mise à Jour du Catalogue Gustav

Pour rafraîchir la base locale de données avec les dernières modifications de `https://gustavguideext.chudequebec.ca/` :
```bash
python gustav_crawler.py
```
Le catalogue local `data/gustav_lab_catalog.json` sera automatiquement actualisé.
