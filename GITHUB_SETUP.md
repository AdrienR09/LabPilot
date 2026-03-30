# 🚀 GitHub Setup for LabPilot

Your local repository is ready! Here's how to push it to GitHub.

## 📊 Repository Stats

```
Total Files:     7,713
Size:            ~1GB (includes node_modules)
Commits:         1 (initial commit)
Branch:          main
Status:          Ready to push
```

## 🎯 Step 1: Create GitHub Repository

1. Go to **https://github.com/new**
2. Fill in:
   - **Repository name**: `labpilot`
   - **Description**: `AI-Powered Lab Automation Framework with FastAPI Backend, React Frontend, Qt Manager, and PyQtGraph Visualization`
   - **Visibility**: **Public** (recommended for open-source projects)
   - **DO NOT** initialize with README/License (we already have them)
3. Click **"Create repository"**

## 🔗 Step 2: Connect & Push

After creating the repo, GitHub will show you these options. Run the commands:

### For HTTPS (recommended for simplicity):
```bash
cd /Users/adrien/Documents/Qudi/labpilot

git remote add origin https://github.com/YOUR_USERNAME/labpilot.git
git branch -M main
git push -u origin main
```

### For SSH (if you prefer):
```bash
cd /Users/adrien/Documents/Qudi/labpilot

git remote add origin git@github.com:YOUR_USERNAME/labpilot.git
git branch -M main
git push -u origin main
```

⚠️ **Replace `YOUR_USERNAME` with your actual GitHub username**

## ⏱️ What to Expect

- **First push**: May take **2-5 minutes** (large repo with node_modules)
- **GitHub notification**: "Pushed N refs"
- **Page load**: Might show "Initializing repository" briefly

## ✅ Step 3: Verify

1. Visit: `https://github.com/YOUR_USERNAME/labpilot`
2. You should see:
   - ✅ All files uploaded
   - ✅ README.md displayed
   - ✅ 7,713 files counted
   - ✅ 1 commit in history
   - ✅ LICENSE visible

## 📌 If Using SSH

If SSH key is not set up:

```bash
# Generate SSH key (one-time):
ssh-keygen -t ed25519 -C "your@email.com"

# Add to GitHub: https://github.com/settings/keys
# Then use SSH remote (see Step 2)
```

## 🎨 After Pushing: Repository Setup

Once on GitHub, consider:

1. **Add Repository Topics** (Settings → About):
   - `python`, `fastapi`, `react`, `qt`, `pyqtgraph`
   - `lab-automation`, `data-acquisition`, `ai`

2. **Enable GitHub Pages** (Settings → Pages → main branch /root)

3. **Add Project Description** (Settings → About)

4. **Protect Main Branch** (Settings → Branches):
   - Require pull request reviews
   - Require status checks to pass

5. **Enable GitHub Actions** for CI/CD (optional)

## 📦 Repository Structure on GitHub

```
labpilot/
├── backend/              # FastAPI server
│   ├── main.py          # API entry point
│   ├── routes/          # API endpoints
│   └── requirements.txt  # Python dependencies
├── frontend/            # React application
│   ├── src/            # React components
│   ├── package.json    # Node dependencies
│   └── index.html      # Main HTML
├── qt_frontend/        # Qt manager + PyQtGraph
├── src/               # Python package
├── examples/          # Usage examples
├── tests/            # Test suite
├── docs/             # Documentation
├── README.md         # Main documentation
├── LICENSE           # MIT License
└── pyproject.toml    # Python config
```

## 🔐 Sensitive Files

Verify `.gitignore` includes:
- ✅ `node_modules/` (checked)
- ✅ `.env` files
- ✅ Built files (`dist/`, `build/`)
- ✅ `__pycache__/`
- ✅ Virtual environments

Current `.gitignore` covers all of these.

## 🚨 Important Notes

1. **Size Warning**: Repo is ~1GB due to node_modules
   - Consider: Add `.gitignore` rule to exclude node_modules before pushing (optional)
   - Or: Push as-is (works fine, just slower first time)

2. **node_modules Workaround** (if wanted):
   ```bash
   # Before pushing, optionally:
   echo "node_modules/" >> .gitignore
   git rm -r --cached node_modules/
   git commit -m "remove node_modules"
   git push -u origin main
   ```
   Then people can do `npm install` after cloning.

3. **First Push Speed**: Large repos take longer (2-5 min typical)

## 🎓 Development Workflow

Once on GitHub:

```bash
# Create feature branch
git checkout -b feature/your-feature-name

# Make changes and commit
git commit -m "feat: your feature"

# Push to GitHub
git push origin feature/your-feature-name

# Create Pull Request on GitHub
```

## 🆘 If Something Goes Wrong

```bash
# Check remote configuration
git remote -v

# Remove wrong remote
git remote remove origin

# Add correct remote
git remote add origin https://github.com/YOUR_USERNAME/labpilot.git

# Try push again
git push -u origin main
```

## 📞 Support

If you need help:
1. Check GitHub docs: https://docs.github.com/en/get-started/importing-your-projects-to-github
2. Verify your username at: https://github.com/settings/profile
3. Check SSH keys at: https://github.com/settings/keys (if using SSH)

---

**Ready to push?** Follow Steps 1-3 above and you're live! 🎉

Questions? See the official guide: https://docs.github.com/
