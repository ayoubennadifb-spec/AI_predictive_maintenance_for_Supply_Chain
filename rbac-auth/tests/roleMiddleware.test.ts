import { requireSuperAdmin } from "../src/middleware/roleMiddleware";
import { Role } from "@prisma/client";

function mockReq(role?: Role) {
  return {
    user: role
      ? { userId: "u1", role, isActive: true }
      : undefined,
  } as any;
}

function mockRes() {
  const res: any = {};
  res.status = jest.fn().mockReturnValue(res);
  res.json = jest.fn().mockReturnValue(res);
  return res;
}

describe("requireSuperAdmin", () => {
  it("allows SUPER_ADMIN", () => {
    const req = mockReq(Role.SUPER_ADMIN);
    const res = mockRes();
    const next = jest.fn();

    requireSuperAdmin(req, res, next);
    expect(next).toHaveBeenCalled();
  });

  it("rejects MANAGER", () => {
    const req = mockReq(Role.MANAGER);
    const res = mockRes();
    const next = jest.fn();

    requireSuperAdmin(req, res, next);
    expect(res.status).toHaveBeenCalledWith(403);
  });
});


