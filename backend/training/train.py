"""Generate owned chess examples, freeze the reservoir, fit only a linear readout.

Run from backend: python -m training.train --games 64 --plies 48 --epochs 300
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

import chess
import numpy as np

from app.neural import Connectome, Simulation, DATA, CONFIG
from app.readout import action_indices, HEADS
from .teacher import choose


def collect(graph, games, plies, seed):
    rng = np.random.default_rng(seed)
    records, features = [], []
    for game_id in range(games):
        board = chess.Board()
        for ply in range(plies):
            if board.is_game_over(claim_draw=True):
                break
            teacher = choose(board)
            if board.turn == chess.BLACK:
                sim = Simulation(graph, board)
                for _ in range(10):
                    sim.advance()
                records.append({'game': game_id, 'fen': board.fen(), 'teacher_uci': teacher.uci()})
                features.append(sim.features())
            # Independent game RNG, broad exploration including tactical mistakes.
            legal = sorted(board.legal_moves, key=lambda m: m.uci())
            played = legal[int(rng.integers(len(legal)))] if rng.random() < .45 else teacher
            board.push(played)
        print(f'Collected game {game_id + 1}/{games}: {len(records)} positions', flush=True)
    return records, np.array(features)


def actions(records):
    lists = []
    targets = []
    for record in records:
        legal = sorted(chess.Board(record['fen']).legal_moves, key=lambda m: m.uci())
        lists.append(legal)
        targets.append([m.uci() for m in legal].index(record['teacher_uci']))
    max_legal = max(map(len, lists))
    a = np.zeros((len(records), max_legal, HEADS), dtype=np.float32)
    mask = np.zeros((len(records), max_legal), dtype=bool)
    for i, moves in enumerate(lists):
        for j, move in enumerate(moves):
            a[i, j, list(action_indices(move))] = 1
            mask[i, j] = True
    return a, mask, np.array(targets)


def objective(x, a, mask, targets, w):
    scores = np.einsum('nla,na->nl', a, x @ w, optimize=True)
    scores[~mask] = -1e9
    scores -= scores.max(axis=1, keepdims=True)
    probs = np.exp(scores)
    probs /= probs.sum(axis=1, keepdims=True)
    n = len(x)
    loss = -np.log(np.maximum(probs[np.arange(n), targets], 1e-30)).mean()
    accuracy = float((probs.argmax(axis=1) == targets).mean())
    residual = probs.copy()
    residual[np.arange(n), targets] -= 1
    head_gradient = np.einsum('nl,nla->na', residual, a, optimize=True) / n
    return float(loss), accuracy, x.T @ head_gradient


def fit(x, a, mask, y, train, val, epochs, seed):
    # Normalization is learned from TRAIN ONLY and belongs to the readout.
    mean = x[train].mean(axis=0)
    scale = np.maximum(x[train].std(axis=0), .05)
    z = np.column_stack(((x - mean) / scale, np.ones(len(x))))
    rng = np.random.default_rng(seed)
    w = rng.normal(0, .002, (z.shape[1], HEADS))
    initial = w.copy()
    m, v = np.zeros_like(w), np.zeros_like(w)
    best, best_loss, best_epoch = w.copy(), float('inf'), 0
    trace = []
    for epoch in range(1, epochs + 1):
        loss, accuracy, gradient = objective(z[train], a[train], mask[train], y[train], w)
        gradient[:-1] += .03 * w[:-1]
        m = .9 * m + .1 * gradient
        v = .999 * v + .001 * gradient ** 2
        w -= .006 * (m / (1 - .9 ** epoch)) / (np.sqrt(v / (1 - .999 ** epoch)) + 1e-8)
        val_loss, val_accuracy, _ = objective(z[val], a[val], mask[val], y[val], w)
        if val_loss < best_loss:
            best, best_loss, best_epoch = w.copy(), val_loss, epoch
        if epoch == 1 or epoch % 10 == 0:
            row = {'epoch': epoch, 'train_loss': loss, 'train_accuracy': accuracy, 'validation_loss': val_loss, 'validation_accuracy': val_accuracy}
            trace.append(row)
            print(json.dumps(row), flush=True)
        if epoch - best_epoch >= 35:
            break
    return best, initial, mean, scale, z, best_epoch, trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--games', type=int, default=64)
    parser.add_argument('--plies', type=int, default=48)
    parser.add_argument('--epochs', type=int, default=300)
    parser.add_argument('--seed', type=int, default=20260910)
    parser.add_argument('--reuse', action='store_true', help='Reuse matching local training dataset')
    args = parser.parse_args()
    if args.games < 10 or args.plies < 2 or args.epochs < 1:
        parser.error('Use at least 10 games, 2 plies, and 1 epoch')
    start = time.monotonic()
    graph = Connectome(load_readout=False)
    frozen = graph.weights.copy()
    cache = Path(__file__).resolve().parents[2] / 'data/training'
    cache.mkdir(parents=True, exist_ok=True)
    dataset_path = cache / 'positions.json'
    expected = {'fingerprint': graph.fingerprint, 'games': args.games, 'plies': args.plies, 'seed': args.seed}
    if args.reuse:
        dataset = json.loads(dataset_path.read_text())
        if dataset['configuration'] != expected:
            raise ValueError('Cached training data configuration mismatch')
        records = dataset['records']
        x = np.load(cache / 'features.npy', allow_pickle=False)
    else:
        records, x = collect(graph, args.games, args.plies, args.seed)
        dataset_path.write_text(json.dumps({'configuration': expected, 'records': records}, indent=2) + '\n')
        np.save(cache / 'features.npy', x)
    # Repeated openings across independent games must not leak across splits.
    # Ignore move clocks when identifying the same chess position.
    seen, keep = set(), []
    for i, record in enumerate(records):
        key = " ".join(record["fen"].split()[:4])
        if key not in seen:
            seen.add(key)
            keep.append(i)
    original_count = len(records)
    records = [records[i] for i in keep]
    x = x[keep]
    # Split by whole game, never adjacent positions across partitions.
    groups = np.random.default_rng(args.seed).permutation(args.games)
    cut1, cut2 = int(args.games * .7), int(args.games * .85)
    split_games = {'train': groups[:cut1], 'validation': groups[cut1:cut2], 'test': groups[cut2:]}
    split = {name: np.array([r['game'] in ids for r in records]) for name, ids in split_games.items()}
    if any(not indexes.any() for indexes in split.values()):
        raise ValueError('Empty dataset split')
    a, mask, y = actions(records)
    w, initial, mean, scale, z, epoch, trace = fit(x, a, mask, y, split['train'], split['validation'], args.epochs, args.seed)
    results = {}
    for name, indexes in split.items():
        loss, acc, _ = objective(z[indexes], a[indexes], mask[indexes], y[indexes], w)
        results[name] = {'positions': int(indexes.sum()), 'games': [int(i) for i in split_games[name]], 'cross_entropy': loss, 'teacher_top1_agreement': acc}
    test = split['test']
    initial_loss, initial_acc, _ = objective(z[test], a[test], mask[test], y[test], initial)
    zero = np.zeros_like(z[test]); zero[:, -1] = 1
    ablation_loss, ablation_acc, _ = objective(zero, a[test], mask[test], y[test], w)
    np.testing.assert_array_equal(graph.weights, frozen)
    out = DATA / 'readout.npz'
    np.savez_compressed(out, weights=w, mean=mean, scale=scale, reservoir_fingerprint=np.array(graph.fingerprint))
    report = {
        'schema_version': 1, 'reservoir_fingerprint': graph.fingerprint, 'reservoir_configuration': CONFIG,
        'checkpoint_sha256': hashlib.sha256(out.read_bytes()).hexdigest(),
        'dataset_sha256': hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        'teacher': 'training.teacher: deterministic two-ply minimax, handcrafted material/center/pawn-advance evaluation; not Stockfish',
        'training': vars(args), 'raw_positions': original_count, 'unique_positions': len(records), 'deduplication': 'Global first occurrence of FEN first four fields before game-group splitting', 'selected_epoch': epoch, 'trainable_parameters': int(w.size),
        'frozen_reservoir_verified': True, 'splits': results,
        'baselines': {'untrained_readout': {'test_cross_entropy': initial_loss, 'test_teacher_top1_agreement': initial_acc},
                      'mean_activity_ablation': {'test_cross_entropy': ablation_loss, 'test_teacher_top1_agreement': ablation_acc},
                      'uniform_legal': {'expected_test_teacher_top1_agreement': float((1 / mask[test].sum(axis=1)).mean())}},
        'limitations': 'Offline imitation of a weak engineered teacher. No Elo or biological learning claim. Mean-activity ablation is not a trained random-topology control. No online learning.',
        'elapsed_seconds': time.monotonic() - start, 'trace': trace,
    }
    (DATA / 'training_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'trace'}, indent=2), flush=True)


if __name__ == '__main__':
    main()
