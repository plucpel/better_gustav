# Extension Chrome GUSTAV - Passerelle Medesync

Cette extension Chrome (Manifest V3) connecte de façon sécurisée votre DME Medesync (Telus Santé) à votre calculateur de prélèvements **GUSTAV**.

---

## 🚀 Installation dans Google Chrome (Poste Clinique)

1. Ouvrez Google Chrome et rendez-vous sur : `chrome://extensions/`
2. Activez le **Mode développeur** (interrupteur en haut à droite).
3. Cliquez sur **« Charger l'extension non empaquetée »** (*Load unpacked*).
4. Sélectionnez le dossier :
   📁 `/Users/ppelleti/Documents/Gustav/extension/`

---

## ⚙️ Configuration

1. Cliquez sur l'icône de l'extension **GUSTAV** dans la barre d'outils Chrome.
2. Vérifiez ou personnalisez :
   * **URL du Serveur GUSTAV** : `http://chatterbox:8000` (ou votre domaine Cloudflare `https://gustav.votreclinique.com`).
   * **Clé Secrète Clinique** : `gustav_ext_secret_chatterbox_2026` (ou celle définie dans les variables d'environnement de votre serveur).
3. Cliquez sur **« Tester la Connexion »** pour valider l'authentification.

---

## 📋 Utilisation Quotidienne

1. Ouvrez n'importe quel dossier patient dans Medesync (`https://secure2.medesync.com/...`).
2. Le bouton **`[ 🧪 GUSTAV ]`** apparaît automatiquement dans la bannière du patient.
3. Un simple clic ouvre instantanément GUSTAV dans un nouvel onglet avec :
   * **Bypass automatique du PIN** (authentification instantanée sans mot de passe).
   * **Pré-remplissage complet** : Nom, RAMQ, Date de naissance, Sexe, No dossier et Prescripteur.
   * **Sécurité totale** : 0 renseignement personnel dans l'URL ou l'historique du navigateur.
