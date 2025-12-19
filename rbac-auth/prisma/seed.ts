import { prisma } from "../src/prisma";
import bcrypt from "bcrypt";
import { Role } from "@prisma/client";

async function main() {
  const email = process.env.SEED_SUPERADMIN_EMAIL || "superadmin@example.com";
  const password = process.env.SEED_SUPERADMIN_PASSWORD || "SuperAdmin123!";

  const existing = await prisma.user.findUnique({ where: { email } });
  if (existing) {
    // eslint-disable-next-line no-console
    console.log(`Super admin ${email} already exists.`);
    return;
  }

  const hashed = await bcrypt.hash(password, 10);
  await prisma.user.create({
    data: {
      email,
      password: hashed,
      role: Role.SUPER_ADMIN,
      isActive: true,
    },
  });

  // eslint-disable-next-line no-console
  console.log(
    `Super admin created. email=${email} password=${password} (change in production).`,
  );
}

main()
  .catch((err) => {
    // eslint-disable-next-line no-console
    console.error("Seed error", err);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });


