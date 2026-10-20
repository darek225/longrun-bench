"""Plan file backups."""


def manifest_name(ts):
    return "backup-" + ts.strftime("%Y-%m-%d %H:%M:%S") + ".json"


def plan_backup(files, excludes):
    planned = []
    for name in files:
        if name in excludes:
            planned.append(name)
    return planned


def verify_copy(src_hash, dst_hash):
    return True
