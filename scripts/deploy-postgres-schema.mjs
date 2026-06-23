import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, '..');
const schemaPath = path.join(projectRoot, 'database', 'postgres_schema.sql');
const migrationsDir = path.join(projectRoot, 'database', 'migrations');

if (!process.env.DATABASE_URL) {
  console.log('DATABASE_URL is not set; skipping PostgreSQL schema deploy.');
  process.exit(0);
}

const { default: pg } = await import('pg');
const { Pool } = pg;
const pool = new Pool({ connectionString: process.env.DATABASE_URL });

async function applySqlFile(filePath) {
  const relativePath = path.relative(projectRoot, filePath).replaceAll(path.sep, '/');
  const sql = fs.readFileSync(filePath, 'utf8');
  await pool.query(sql);
  console.log(`Applied ${relativePath}`);
}

async function deploySchema() {
  try {
    await applySqlFile(schemaPath);

    if (fs.existsSync(migrationsDir)) {
      const migrations = fs.readdirSync(migrationsDir)
        .filter((name) => name.endsWith('.sql'))
        .sort();

      for (const migration of migrations) {
        await applySqlFile(path.join(migrationsDir, migration));
      }
    }

    console.log('PostgreSQL schema deploy completed.');
  } catch (error) {
    console.error('PostgreSQL schema deploy failed:', error.message);
    process.exitCode = 1;
  } finally {
    await pool.end();
  }
}

deploySchema();
