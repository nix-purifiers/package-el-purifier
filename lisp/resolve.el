;;; resolve.el --- Resolve an Emacs package declaration -*- lexical-binding: t; -*-
;; SPDX-License-Identifier: MIT
(require 'package)
(require 'json)
(let* ((manifest (getenv "PACKAGE_EL_PURIFIER_MANIFEST"))
       (destination (getenv "PACKAGE_EL_PURIFIER_RESOLUTION"))
       (package-user-dir (make-temp-file "package-el-purifier-elpa-" t))
       (package-directory-list nil)
       (package--initialized t)
       (package-alist nil)
       (package-archive-contents nil)
       (package-enable-at-startup nil))
  (unwind-protect
      (progn
        (load manifest nil t)
        (package-refresh-contents)
        ;; Let package.el solve normally, with unrequested packages pinned to
        ;; their existing native descriptors. An incompatible pin fails rather
        ;; than silently upgrading an additional package.
        (when-let* ((pins (getenv "PACKAGE_EL_PURIFIER_PINS")))
          (let ((records (with-temp-buffer
                           (insert-file-contents pins)
                           (json-parse-buffer :object-type 'alist :array-type 'list))))
            (dolist (record records)
              (let* ((name (intern (alist-get 'name record)))
                     (archive (concat "pinned-" (symbol-name name)))
                     (url (alist-get 'url record)))
                (push (cons archive (file-name-directory url)) package-archives)
                (setf (alist-get name package-archive-contents)
                      (list (package-desc-create
                             :name name :version (alist-get 'versionList record)
                             :reqs (mapcar (lambda (req) (list (intern (car req)) (cadr req)))
                                           (alist-get 'requirements record))
                             :summary (alist-get 'summary record)
                             :kind (intern (alist-get 'kind record)) :archive archive)))))))
        (let ((transaction
               (package-compute-transaction
                nil
                (mapcar (lambda (name) (list name '(0)))
                        package-selected-packages))))
          (with-temp-file destination
            (insert
             (json-serialize
              `((emacsVersion . ,emacs-version)
                (builtins . ,(vconcat (mapcar (lambda (req) (vector (symbol-name (car req)) (vconcat (cdr req)))) package--builtin-versions)))
                (selected . ,(vconcat (mapcar #'symbol-name package-selected-packages)))
                (packages .
                          ,(vconcat
                            (mapcar
                             (lambda (desc)
                               (let ((archive (cdr (assoc (package-desc-archive desc) package-archives))))
                                 `((name . ,(symbol-name (package-desc-name desc)))
                                   (version . ,(package-version-join (package-desc-version desc)))
                                   (versionList . ,(vconcat (package-desc-version desc)))
                                   (requirements .
                                                 ,(vconcat
                                                   (mapcar (lambda (req) (vector (symbol-name (car req)) (vconcat (cadr req))))
                                                           (package-desc-reqs desc))))
                                   (summary . ,(package-desc-summary desc))
                                   (kind . ,(symbol-name (package-desc-kind desc)))
                                   (archive . ,archive))))
                             transaction)))))))))
    (delete-directory package-user-dir t)))
