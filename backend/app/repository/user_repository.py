"""用户仓库。"""

from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    """用户表数据访问。"""

    def __init__(self, db: Session) -> None:
        self._db: Session = db

    def get_by_id(self, user_id: int) -> User | None:
        """按 ID 查询用户。"""

        return self._db.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        """按用户名查询用户。"""

        return self._db.query(User).filter(User.username == username).first()

    def get_by_email(self, email: str) -> User | None:
        """按邮箱查询用户。"""

        return self._db.query(User).filter(User.email == email).first()

    def create(self, username: str, hashed_password: str, email: str | None = None) -> User:
        """创建新用户。"""

        user = User(username=username, hashed_password=hashed_password, email=email)
        self._db.add(user)
        self._db.commit()
        self._db.refresh(user)
        return user
