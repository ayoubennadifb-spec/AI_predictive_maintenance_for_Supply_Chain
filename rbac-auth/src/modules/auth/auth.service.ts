import { prisma } from "../../prisma";
import bcrypt from "bcrypt";
import jwt from "jsonwebtoken";
import { config } from "../../config";
import { Role } from "@prisma/client";
import { add } from "date-fns";

export interface Tokens {
  accessToken: string;
  refreshToken: string;
}

export class AuthService {
  async validateUser(email: string, password: string) {
    const user = await prisma.user.findUnique({ where: { email } });
    if (!user) return null;
    const isMatch = await bcrypt.compare(password, user.password);
    if (!isMatch) return null;
    if (!user.isActive) {
      throw new Error("INACTIVE");
    }
    return user;
  }

  private signAccessToken(userId: string, role: Role, isActive: boolean): string {
    return jwt.sign(
      { userId, role, isActive },
      config.jwtAccessSecret,
      { expiresIn: config.accessTokenTtl },
    );
  }

  private async signRefreshToken(userId: string): Promise<string> {
    const expires = add(new Date(), { days: 7 });
    const token = jwt.sign(
      { userId },
      config.jwtRefreshSecret,
      { expiresIn: config.refreshTokenTtl },
    );
    await prisma.refreshToken.create({
      data: {
        userId,
        token,
        expiresAt: expires,
      },
    });
    return token;
  }

  async login(email: string, password: string): Promise<Tokens> {
    const user = await this.validateUser(email, password);
    if (!user) {
      throw new Error("INVALID_CREDENTIALS");
    }

    const accessToken = this.signAccessToken(user.id, user.role, user.isActive);
    const refreshToken = await this.signRefreshToken(user.id);
    return { accessToken, refreshToken };
  }

  async refresh(oldRefreshToken: string): Promise<Tokens> {
    let payload: { userId: string } | null = null;
    try {
      payload = jwt.verify(oldRefreshToken, config.jwtRefreshSecret) as { userId: string };
    } catch {
      throw new Error("INVALID_REFRESH");
    }

    const stored = await prisma.refreshToken.findUnique({
      where: { token: oldRefreshToken },
      include: { user: true },
    });
    if (!stored || !stored.user) {
      throw new Error("INVALID_REFRESH");
    }
    if (stored.expiresAt < new Date()) {
      throw new Error("EXPIRED_REFRESH");
    }

    const user = stored.user;
    if (!user.isActive) {
      throw new Error("INACTIVE");
    }

    // Optionally revoke old token
    await prisma.refreshToken.delete({ where: { token: oldRefreshToken } });

    const accessToken = this.signAccessToken(user.id, user.role, user.isActive);
    const refreshToken = await this.signRefreshToken(user.id);
    return { accessToken, refreshToken };
  }
}

export const authService = new AuthService();


