// static/script.js

document.addEventListener('DOMContentLoaded', () => {
    // --- DOM element references ---
    const directoryPicker = document.getElementById('directoryPicker');
    const analyzeBtn = document.getElementById('analyzeBtn');
    const analyzeSpinner = document.getElementById('analyze-spinner');
    const analyzeError = document.getElementById('analyze-error');
    const analyzeStatusContainer = document.getElementById('analyze-status');

    const fileSelectionSection = document.getElementById('file-selection-section');
    const fileListDiv = document.getElementById('fileList');
    const selectAllBtn = document.getElementById('selectAllBtn');
    const deselectAllBtn = document.getElementById('deselectAllBtn');

    const generationSection = document.getElementById('generation-section');
    const generateBtn = document.getElementById('generateBtn');
    const generateSpinner = document.getElementById('generate-spinner');
    const generateError = document.getElementById('generate-error');
    const enableSecretMaskingCheckbox = document.getElementById('enableSecretMasking');

    const resultArea = document.getElementById('resultArea');
    const markdownOutput = document.getElementById('markdownOutput');
    const summaryContainer = document.getElementById('summaryContainer');
    const copyBtn = document.getElementById('copyBtn');

    // --- State variables ---
    let currentFilesData = []; // Will store uploaded files (object with name, full relative path and content)
    let includedFilePaths = []; // Will store only the included file paths (not ignored by gitignore)

    // --- Utility functions ---
    function showElement(element) { element?.classList.remove('visually-hidden'); }
    function hideElement(element) { element?.classList.add('visually-hidden'); }
    function showError(errorElement, message, statusContainer) {
        if (errorElement) { errorElement.textContent = message; showElement(errorElement); }
        hideElement(statusContainer?.querySelector('.spinner-border'));
    }
    function hideError(errorElement) { hideElement(errorElement); if (errorElement) errorElement.textContent = ''; }
    function showSpinner(spinnerElement) { showElement(spinnerElement); }
    function hideSpinner(spinnerElement) { hideElement(spinnerElement); }

    // --- Directory analysis (upload of selected files) ---
    analyzeBtn.addEventListener('click', async () => {
        const files = directoryPicker.files;
        if (!files || files.length === 0) {
            showError(analyzeError, "Please select a directory.", analyzeStatusContainer);
            return;
        }
        hideError(analyzeError);
        showSpinner(analyzeSpinner);
        hideElement(fileSelectionSection);
        hideElement(generationSection);
        hideElement(resultArea);
        fileListDiv.innerHTML = '<p class="text-muted text-center placeholder-message">Analyzing...</p>';
        currentFilesData = [];
        includedFilePaths = [];

        // Read all files using FileReader and retrieve their full relative path
        const readFilePromises = [];
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            readFilePromises.push(new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => {
                    resolve({
                        name: file.name,
                        // webkitRelativePath contains the full relative path from the selected directory
                        path: file.webkitRelativePath || file.name,
                        content: reader.result
                    });
                };
                reader.onerror = () => {
                    reject(new Error(`Error reading file ${file.name}`));
                };
                reader.readAsText(file);
            }));
        }

        try {
            const uploadedFiles = await Promise.all(readFilePromises);
            currentFilesData = uploadedFiles;
            // Send the uploaded data to the server to build the file tree and apply .gitignore rules
            const response = await fetch('/upload', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                body: JSON.stringify({ files: uploadedFiles })
            });
            const data = await response.json();
            if (!response.ok || !data.success) {
                throw new Error(data.error || `Error ${response.status}`);
            }
            
            // Store the list of included file paths (not ignored)
            includedFilePaths = data.files.map(f => f.path);
            
            // Render the file tree
            renderFileList(data.files);
            
            showElement(fileSelectionSection);
            showElement(generationSection);
        } catch (error) {
            console.error("Analysis error:", error);
            showError(analyzeError, `Analysis error: ${error.message}`, analyzeStatusContainer);
            fileListDiv.innerHTML = '<p class="text-danger text-center placeholder-message">Analysis failed.</p>';
            showElement(fileSelectionSection);
        } finally {
            hideSpinner(analyzeSpinner);
        }
    });

    // --- Render file tree ---
    function renderFileList(files) {
        fileListDiv.innerHTML = '';
        if (files.length === 0) {
            fileListDiv.innerHTML = '<p class="text-muted text-center placeholder-message">No non-ignored files found.</p>';
            return;
        }
        
        // Build tree structure from paths (files already contains only non-ignored files)
        const paths = files.map(f => f.path);
        const tree = buildTreeStructure(paths);
        
        // Create the DOM element for the tree
        const ul = createTreeElement(tree, "");
        fileListDiv.appendChild(ul);
        
        // Add an explanatory note for the user
        const noteDiv = document.createElement('div');
        noteDiv.className = 'alert alert-info mt-3';
        noteDiv.innerHTML = '<small><i class="fas fa-info-circle"></i> Note: Only files not ignored by .gitignore rules are displayed and selected.</small>';
        fileListDiv.appendChild(noteDiv);
    }

    // Construct a tree structure from relative paths
    function buildTreeStructure(paths) {
        const tree = {};
        paths.forEach(path => {
            let currentLevel = tree;
            const parts = path.split('/');
            parts.forEach((part, index) => {
                if (!part) return;
                const isLastPart = (index === parts.length - 1);
                if (!currentLevel[part]) {
                    // If not the last part, create an object to contain children
                    currentLevel[part] = isLastPart ? true : { _children: {} };
                }
                if (!isLastPart && typeof currentLevel[part] === 'object') {
                    currentLevel = currentLevel[part]._children;
                }
            });
        });
        return tree;
    }

    // --- Create the tree structure while preserving full path and selecting by default ---
    function createTreeElement(node, basePath) {
        const ul = document.createElement('ul');
        const keys = Object.keys(node).sort();
        keys.forEach(key => {
            // Calculate the full path for the current node
            const fullPath = basePath ? `${basePath}/${key}` : key;
            const li = document.createElement('li');
            const div = document.createElement('div');
            div.classList.add('form-check');

            const input = document.createElement('input');
            input.type = 'checkbox';
            input.classList.add('form-check-input');
            // Using the full path as the value (e.g., "static/script.js")
            input.value = fullPath;
            // Select by default only files that are in the included file paths list
            // For folders, always select by default
            input.checked = true;

            const label = document.createElement('label');
            label.classList.add('form-check-label');
            label.textContent = key;

            div.appendChild(input);
            div.appendChild(label);
            li.appendChild(div);

            if (node[key] && typeof node[key] === 'object' && node[key]._children && Object.keys(node[key]._children).length > 0) {
                li.classList.add('folder');
                // Recursive call passing the fullPath to accumulate the full path
                const childrenUl = createTreeElement(node[key]._children, fullPath);
                li.appendChild(childrenUl);
            } else {
                li.classList.add('file');
            }
            ul.appendChild(li);
        });
        return ul;
    }

    // --- Handling selection via checkboxes ---
    fileListDiv.addEventListener('change', (event) => {
        if (event.target.matches('.form-check-input')) {
            const checkbox = event.target;
            const isChecked = checkbox.checked;
            const parentLi = checkbox.closest('li');
            if (parentLi && parentLi.classList.contains('folder')) {
                const childCheckboxes = parentLi.querySelectorAll('ul .form-check-input');
                childCheckboxes.forEach(child => {
                    child.checked = isChecked;
                });
            }
        }
    });

    selectAllBtn.addEventListener('click', () => {
        fileListDiv.querySelectorAll('.form-check-input').forEach(cb => {
            cb.checked = true;
        });
    });
    deselectAllBtn.addEventListener('click', () => {
        fileListDiv.querySelectorAll('.form-check-input').forEach(cb => {
            cb.checked = false;
        });
    });

    // Function to format numbers with thousands separators
    function formatNumber(num) {
        return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
    }

    // --- Generate context ---
    generateBtn.addEventListener('click', async () => {
        const selectedCheckboxes = fileListDiv.querySelectorAll('.form-check-input:checked');
        // The value of each checkbox is the full path of the selected file
        let selectedFiles = Array.from(selectedCheckboxes).map(cb => cb.value);
        
        // Filter the selected paths to keep only those in includedFilePaths
        selectedFiles = selectedFiles.filter(path => includedFilePaths.includes(path));
        
        if (selectedFiles.length === 0) {
            showError(generateError, "Please select at least one file.", null);
            hideElement(resultArea);
            return;
        }
        hideError(generateError);
        showSpinner(generateSpinner);
        hideElement(resultArea);
        markdownOutput.value = "Generating context...";
        summaryContainer.innerHTML = "";
        document.getElementById('secretsMaskedAlert').classList.add('d-none');
        
        // Récupérer la configuration de masquage des secrets
        const enableSecretMasking = enableSecretMaskingCheckbox 
            ? enableSecretMaskingCheckbox.checked 
            : true; // Activé par défaut si le checkbox n'existe pas

        try {
            const response = await fetch('/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                body: JSON.stringify({ 
                    selected_files: selectedFiles,
                    masking_options: {
                        enable_masking: enableSecretMasking
                    }
                })
            });
            const data = await response.json();
            if (!response.ok || !data.success) {
                throw new Error(data.error || `Error ${response.status}`);
            }
            
            // Display the markdown context
            markdownOutput.value = data.markdown || "";

            // Afficher l'alerte de sécurité si des secrets ont été masqués
            if (data.summary && data.summary.secrets_masked > 0) {
                const secretsAlert = document.getElementById('secretsMaskedAlert');
                const secretsDetails = document.getElementById('secretsMaskedDetails');
                
                // Afficher les détails
                secretsDetails.innerHTML = `
                    <li><strong>${data.summary.secrets_masked}</strong> sensitive items masked</li>
                    <li><strong>${data.summary.files_with_secrets}</strong> of ${data.summary.files_count} files contained sensitive data</li>
                `;
                
                // Afficher l'alerte
                secretsAlert.classList.remove('d-none');
            }
            
            // Display the summary separately
            if (data.summary) {
                const summary = data.summary;
                
                // Ajouter une information sur les secrets masqués si applicable
                const secretsMaskedInfo = summary.secrets_masked > 0 
                    ? `<li>Sensitive data masked: ${summary.secrets_masked} items in ${summary.files_with_secrets} files</li>` 
                    : '';
                
                summaryContainer.innerHTML = `
                <div class="alert alert-primary">
                    <h6><i class="fas fa-info-circle"></i> Context summary</h6>
                    <ul class="mb-0">
                        ${secretsMaskedInfo}
                        <li>Number of files: ${summary.files_count}</li>
                        <li>Number of characters: ${formatNumber(summary.char_count)}</li>
                        <li>Estimated tokens: ~${formatNumber(summary.estimated_tokens)}</li>
                        <li>Compatibility: ${summary.model_compatibility}</li>
                    </ul>
                    <div class="mt-2">
                        <small class="text-muted">Note: This estimation is approximate and may vary depending on the tokenizer used by the LLM.</small>
                    </div>
                </div>`;
            }
            
            showElement(resultArea);
            copyBtn.disabled = false;
            copyBtn.innerHTML = '<i class="far fa-copy"></i> Copy';
        } catch (error) {
            console.error('Generation error:', error);
            showError(generateError, `Generation error: ${error.message}`);
            markdownOutput.value = "";
            summaryContainer.innerHTML = "";
        } finally {
            hideSpinner(generateSpinner);
        }
    });

    // --- Copy the generated context to the clipboard ---
    copyBtn.addEventListener('click', async () => {
        if (!markdownOutput.value) return;
        try {
            await navigator.clipboard.writeText(markdownOutput.value);
            copyBtn.innerHTML = '<i class="fas fa-check"></i> Copied!';
            copyBtn.classList.add('copied-feedback');
            copyBtn.disabled = true;
            setTimeout(() => {
                copyBtn.innerHTML = '<i class="far fa-copy"></i> Copy';
                copyBtn.classList.remove('copied-feedback');
                copyBtn.disabled = false;
            }, 1500);
        } catch (err) {
            console.error('Copy error:', err);
            alert('Error: Unable to copy to clipboard.');
        }
    });
});