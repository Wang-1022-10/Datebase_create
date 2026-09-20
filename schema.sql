-- SQLite 示例结构（论文离线预测 + 本车状态分表写入）

CREATE TABLE IF NOT EXISTS ego_state (
    frame_id INTEGER NOT NULL PRIMARY KEY,
    x        REAL NOT NULL,
    y        REAL NOT NULL,
    v        REAL NOT NULL,
    a        REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS predictions (
    frame_id         INTEGER NOT NULL,
    target_id        TEXT    NOT NULL,
    trajectory_index INTEGER NOT NULL,
    probability      REAL    NOT NULL,
    t                REAL    NOT NULL,
    x                REAL    NOT NULL,
    y                REAL    NOT NULL,
    PRIMARY KEY (frame_id, target_id, trajectory_index, t)
);

CREATE INDEX IF NOT EXISTS idx_predictions_frame ON predictions(frame_id);
