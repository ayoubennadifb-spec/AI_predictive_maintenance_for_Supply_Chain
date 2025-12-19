import { AuthService } from "../src/modules/auth/auth.service";
import { prisma } from "../src/prisma";
import bcrypt from "bcrypt";

jest.mock("../src/prisma", () => {
  return {
    prisma: {
      user: {
        findUnique: jest.fn(),
      },
      refreshToken: {
        create: jest.fn(),
        findUnique: jest.fn(),
        delete: jest.fn(),
      },
    },
  };
});

jest.mock("bcrypt");

describe("AuthService", () => {
  const service = new AuthService();

  beforeEach(() => {
    jest.resetAllMocks();
  });

  it("throws on invalid credentials when user not found", async () => {
    (prisma.user.findUnique as jest.Mock).mockResolvedValue(null);
    await expect(service.login("nope@example.com", "badpass")).rejects.toThrow(
      "INVALID_CREDENTIALS",
    );
  });

  it("throws on invalid credentials when password does not match", async () => {
    (prisma.user.findUnique as jest.Mock).mockResolvedValue({
      id: "u1",
      email: "user@example.com",
      password: "hashed",
      role: "MANAGER",
      isActive: true,
    });
    (bcrypt.compare as unknown as jest.Mock).mockResolvedValue(false);

    await expect(service.login("user@example.com", "badpass")).rejects.toThrow(
      "INVALID_CREDENTIALS",
    );
  });
});



