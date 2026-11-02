;;; package-el-purifier.el --- Nix-resolved package.el dependencies -*- lexical-binding: t; -*-
;; Copyright (C) 2026 the nix-purifier developers
;; SPDX-License-Identifier: MIT
;; Version: 0.1.0
;; Package-Requires: ((emacs "29.1"))
;; URL: https://nix-purifiers.github.io/
;; Keywords: tools, package

;;; Commentary:
;; Activate before installing/loading the configuration's packages.  The Nix
;; wrapper does this before init.el; a native installation can enable the mode
;; in early-init.el.  With no lock, ordinary package.el resolution is retained.

;;; Code:
(require 'package)
(require 'json)
(require 'subr-x)

(defgroup package-el-purifier nil "Nix-resolved Emacs packages." :group 'package)
(defcustom package-el-purifier-directory nil
  "Configuration root, or nil for `user-emacs-directory'."
  :type '(choice (const nil) directory))
(defvar package-el-purifier--archive nil)
(defvar package-el-purifier--packages nil)
(defvar package-el-purifier--nix-delivered nil)
(defvar package-el-purifier-mode nil)

(defun package-el-purifier--refresh (original &rest arguments)
  "Call ORIGINAL with ARGUMENTS against the locked local archive."
  (if package-el-purifier--archive
      ;; Refreshing normally writes archive-contents under package-user-dir.
      ;; Our prebuilt, hash-verified copy is immutable and already current.
      (let ((package-archives `(("purified" . ,package-el-purifier--archive))))
        (package-read-all-archive-contents))
    (apply original arguments)))

(defun package-el-purifier--install (original package &rest arguments)
  "Call ORIGINAL on PACKAGE and ARGUMENTS only when it is locked."
  (let ((name (if (package-desc-p package) (package-desc-name package) package)))
    (when (and package-el-purifier--archive
               (not (memq name package-el-purifier--packages))
               (not (package-built-in-p name)))
      (user-error "Package %s is not locked; add it to packages.el and run package-el-purifier lock" name))
    (if package-el-purifier--archive
        (unless (package-installed-p name)
          (user-error "Locked package %s is unavailable; run package-el-purifier prefetch" name))
      (apply original package arguments))))

(defun package-el-purifier--activate-environment (directory)
  "Activate the Nix-built package environment in DIRECTORY."
  (let ((metadata (with-temp-buffer
                    (insert-file-contents (expand-file-name "metadata.json" directory))
                    (json-parse-buffer :object-type 'alist :array-type 'list))))
    (unless (equal emacs-version (alist-get 'emacsVersion metadata))
      (user-error "Locked packages need Emacs %s; use the Nix Emacs wrapper"
                  (alist-get 'emacsVersion metadata)))
    (setq package-user-dir (expand-file-name "elpa" directory)
          package-directory-list nil
          package-quickstart t
          package-quickstart-file (expand-file-name "package-quickstart.el" directory)
          package-el-purifier--archive (alist-get 'archive metadata)
          package-el-purifier--packages (mapcar #'intern (alist-get 'packages metadata))
          package-archives `(("purified" . ,package-el-purifier--archive))
          package-el-purifier-mode t)
    (unless (advice-member-p #'package-el-purifier--refresh 'package-refresh-contents)
      (advice-add 'package-refresh-contents :around #'package-el-purifier--refresh))
    (unless (advice-member-p #'package-el-purifier--install 'package-install)
      (advice-add 'package-install :around #'package-el-purifier--install))
    (package-initialize)))

(defun package-el-purifier-activate ()
  "Prepare and activate locked package dependencies for this configuration."
  (interactive)
  (unless (getenv "PACKAGE_EL_PURIFIER_LOCKING")
    (let* ((default-directory (file-name-as-directory
                               (or package-el-purifier-directory user-emacs-directory)))
           (lockfile (or (getenv "PACKAGE_EL_PURIFIER_LOCKFILE")
                         (expand-file-name "package-el-purifier.lock.json"))))
      (if (not (file-exists-p lockfile))
          (display-warning 'package-el-purifier
                           "No lockfile; using ordinary, impure package.el resolution")
        (unless package-el-purifier--nix-delivered
          (display-warning 'package-el-purifier
                           "Plugin resolved impurely; use the Nix Emacs wrapper for pure plugin resolution"))
        (let* ((cli (executable-find "package-el-purifier"))
               (program (or cli (executable-find "nix")))
               (arguments (append (unless cli '("run" "github:nix-purifiers/package-el-purifier" "--"))
                                  (list "--lockfile" lockfile "prefetch" "--json")))
               (errors (make-temp-file "package-el-purifier-errors-")))
          (unless program (user-error "package-el-purifier requires Nix"))
          (unwind-protect
              (with-temp-buffer
                (unless (zerop (apply #'call-process program nil (list t errors) nil arguments))
                  (user-error "package-el-purifier failed: %s"
                              (with-temp-buffer (insert-file-contents errors) (buffer-string))))
                (goto-char (point-min))
                (let* ((data (json-parse-buffer :object-type 'alist))
                       (environment (alist-get 'environment data)))
                  (package-el-purifier--activate-environment environment)))
            (delete-file errors)))))))

;;;###autoload
(define-minor-mode package-el-purifier-mode
  "Use locked Nix-resolved package.el dependencies."
  :global t
  :group 'package-el-purifier
  (if package-el-purifier-mode
      (package-el-purifier-activate)
    (advice-remove 'package-refresh-contents #'package-el-purifier--refresh)
    (advice-remove 'package-install #'package-el-purifier--install)
    (setq package-el-purifier--archive nil)))

(provide 'package-el-purifier)
;;; package-el-purifier.el ends here
